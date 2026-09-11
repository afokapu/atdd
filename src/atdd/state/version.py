"""Release version as a State Store concern (#1172).

The State Store is the **local source of truth** for the release version. The
singleton ``release`` object (uid=``release``, seeded by migration v2) carries
the authoritative current value in ``data.version``; every bump records a
``version_bumped`` event so the history is auditable:

- :func:`current`               — the authoritative current version string.
- :func:`next_from_change_class` — the next version for a PATCH/MINOR/MAJOR bump
  (no write).
- :func:`bump`                  — apply a bump: write the object, append the
  ``version_bumped`` event, AND emit a **provider-neutral** ``version_decided``
  outbox signal carrying ``{version, change_class}``; returns the new version.

**Provider-neutral core boundary (#1172 design doc §2/§3; #1171 local-first).**
Core owns the *number* and the *decision* only. On a bump it enqueues a neutral
``version_decided`` outbox message — the operation name and payload name no
provider, no PyPI, no "tag"/"publish", and core writes no git/github ref. The
publication side-effect (create the git tag, publish to the ecosystem, and write
the tag back as an ``external_ref``) lives **entirely in the release extension**
that drains the outbox; none of it is in this module. The outbox ``provider`` is
a configured value (a keyword-only parameter defaulting to ``"github"``, mirroring
:func:`atdd.state.hub.promote_trace`); *this* repo configures github, another
stack passes its own.

Change-class semantics match ``CLAUDE.md::release.change_class``:
``PATCH`` (bug/docs/refactor), ``MINOR`` (new feature, non-breaking), ``MAJOR``
(breaking change). Dependency discipline: stdlib + ``atdd.state`` only — NO
``atdd.coach`` import (#1220 boundary).
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from atdd.state.projections import RELEASE_UID, VERSION_BUMPED_EVENT
from atdd.state.store import EventStore, ObjectStore, SyncStore

_log = logging.getLogger(__name__)

RELEASE_KIND = "release"
#: The deterministic build-consumable fallback when no release version exists in
#: the store (mirrors the build hook's no-store fallback — see
#: ``build_meta_shim``). PEP 440 local version segment.
LOCAL_FALLBACK_VERSION = "0.0.0+local"

#: Provider-neutral decision signal (#1172 design doc §2/§3). Core enqueues this
#: on a bump; the release extension drains it to tag + publish. The operation
#: name and its payload (``{version, change_class}``) name no provider and no
#: publish mechanics — that coupling lives in the extension, never in core.
VERSION_DECIDED_OPERATION = "version_decided"
#: Default outbox provider — a *configured* value, not provider logic baked into
#: core. Mirrors :func:`atdd.state.hub.promote_trace`'s ``provider="github"``
#: default; this repo configures github, other stacks pass their own.
DEFAULT_PROVIDER = "github"

_CHANGE_CLASSES = ("PATCH", "MINOR", "MAJOR")

#: The default PyPI project the release pipeline reconciles against and the JSON
#: API that carries the authoritative published latest (``.info.version``). The
#: git-ignored State Store never reaches CI (#1172) and git tags drift below the
#: real published latest (manual publishes skip tagging; orphan tags trail failed
#: runs), so PyPI — the published release index — is the pragmatic authoritative
#: base that DOES reach CI. See :func:`resolve_release_base`.
PYPI_PACKAGE = "atdd"
PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"

#: A ``urllib``-style opener: ``opener(url, timeout=...) -> context-manager`` whose
#: body is a readable file-like. Injectable so :func:`latest_on_pypi` is unit-
#: testable without network. Defaults to :func:`urllib.request.urlopen`.
Opener = Callable[..., object]


class VersionError(Exception):
    """Release-version resolution / mutation failure."""


def parse(version: str) -> Tuple[int, int, int]:
    """Parse an ``X.Y.Z`` semver core into an ``(int, int, int)`` triple.

    Ignores any PEP 440 local/pre-release suffix (``+local``, ``-rc1``) so the
    fallback and tagged builds still parse. Raises :class:`VersionError` on a
    value with no parseable ``major.minor.patch`` core.
    """
    core = version.strip().split("+", 1)[0].split("-", 1)[0]
    parts = core.split(".")
    if len(parts) < 3:
        raise VersionError(f"not a semver version: {version!r}")
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError as exc:
        raise VersionError(f"not a semver version: {version!r}") from exc


def _next(major: int, minor: int, patch: int, change_class: str) -> str:
    cls = change_class.upper()
    if cls == "MAJOR":
        return f"{major + 1}.0.0"
    if cls == "MINOR":
        return f"{major}.{minor + 1}.0"
    if cls == "PATCH":
        return f"{major}.{minor}.{patch + 1}"
    raise VersionError(f"unknown change class {change_class!r}; expected one of {_CHANGE_CLASSES}")


def semver_max(*versions: Optional[str]) -> Optional[str]:
    """Return the argument with the greatest semver *core*, or ``None`` if none parse.

    Comparison is numeric on the ``(major, minor, patch)`` triple (so ``3.10.0``
    beats ``3.9.0``, unlike a lexical compare), ignoring any PEP 440 suffix via
    :func:`parse`. ``None``/empty/unparseable arguments are skipped. The winner's
    **original string** is returned unchanged (not a re-serialized core), so a
    tagged or suffixed identity round-trips.
    """
    best: Optional[str] = None
    best_key: Optional[Tuple[int, int, int]] = None
    for version in versions:
        if not version:
            continue
        try:
            key = parse(version)
        except VersionError:
            continue
        if best_key is None or key > best_key:
            best_key, best = key, version
    return best


def latest_on_pypi(
    package: str = PYPI_PACKAGE, *, timeout: float = 10.0, opener: Optional[Opener] = None
) -> Optional[str]:
    """The latest published version of ``package`` on PyPI, or ``None`` on any failure.

    Queries the PyPI JSON API (``/pypi/<package>/json`` → ``.info.version``) using
    stdlib ``urllib`` (keeps this module stdlib + ``atdd.state`` only, #1220). Returns
    ``None`` — never raises — on ANY failure (network unreachable, HTTP error,
    malformed/incomplete payload, unparseable version) so a transient PyPI outage
    falls back to the git tag rather than hard-failing the release. ``opener`` is
    injectable for hermetic tests.
    """
    url = PYPI_JSON_URL.format(package=package)
    fetch = opener or urllib.request.urlopen
    try:
        with fetch(url, timeout=timeout) as resp:  # type: ignore[operator]
            payload = json.load(resp)
        version = payload.get("info", {}).get("version")
        if not version:
            raise ValueError("PyPI payload carries no info.version")
        parse(str(version))  # validate a semver core; reject junk
        return str(version)
    except (urllib.error.URLError, OSError, ValueError, TypeError, KeyError,
            AttributeError, VersionError) as exc:
        _log.warning(
            "PyPI latest-version query failed; falling back to the git tag",
            extra={"package": package, "url": url, "reason": str(exc)},
        )
        return None


# --- release completeness (#1924) -------------------------------------------
#
# A release is THREE artifacts published by separate calls that fail separately:
# a git tag, a PyPI wheel, and a GitHub Release object. `publish.yml` decided
# "already released" from `git describe --exact-match` alone — and the tag is
# created FIRST, so it is the artifact most likely to exist when a later step
# fails. Measured: v4.73.0 and v4.73.1 each carry a tag and a wheel and neither
# has a release object, because `gh release create` hit a rate limit after the
# other two had landed.

COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
ABSENT = "ABSENT"


@dataclass(frozen=True)
class ReleaseArtifacts:
    """What actually exists for one version, observed rather than inferred."""

    tag: bool
    pypi: bool
    github_release: bool

    def missing(self) -> List[str]:
        return [
            name for name, present in (
                ("tag", self.tag),
                ("pypi", self.pypi),
                ("github-release", self.github_release),
            ) if not present
        ]


@dataclass(frozen=True)
class ReleasePlan:
    """What a publish run should do about the version on HEAD."""

    action: str                       # "skip" | "complete" | "publish-new"
    version: Optional[str]
    missing: List[str]
    orphaned: bool = False


def release_state(artifacts: ReleaseArtifacts) -> str:
    """COMPLETE, PARTIAL or ABSENT — never inferred from one artifact."""
    present = (artifacts.tag, artifacts.pypi, artifacts.github_release)
    if all(present):
        return COMPLETE
    if not any(present):
        return ABSENT
    return PARTIAL


def plan_release_action(
    head_version: Optional[str],
    artifacts: ReleaseArtifacts,
    next_version: str,
) -> ReleasePlan:
    """Decide from what exists, not from what a tag implies.

    The `complete` branch is the point. Reporting PARTIAL without it would send
    the run down the ordinary reconcile+bump path, publishing ``next_version``
    and abandoning the half-published one for good — the gate would stop lying
    and the outcome would get worse.

    ``head_version`` is the version the tag on HEAD names. Without a tag there is
    no identity to complete, so artifacts found elsewhere are orphans this commit
    cannot claim: the run proceeds normally and says so. That is the boundary
    #1326's ``max(PyPI, git tag)`` base already covers — it stops the next version
    colliding with an orphan; it does not heal one.
    """
    state = release_state(artifacts)
    if head_version is None:
        return ReleasePlan(
            "publish-new", next_version, [],
            orphaned=state is not ABSENT,
        )
    if state == COMPLETE:
        return ReleasePlan("skip", head_version, [])
    if state == PARTIAL:
        return ReleasePlan("complete", head_version, artifacts.missing())
    return ReleasePlan("publish-new", next_version, [])


def version_on_pypi(
    version: str, package: str = PYPI_PACKAGE, *,
    timeout: float = 10.0, opener: Optional[Opener] = None,
) -> Optional[bool]:
    """Whether ``version`` has a file published on PyPI.

    ``True``/``False`` when PyPI answered, ``None`` when it could not be asked —
    the three-valued return is the point. A network failure is not evidence that
    a wheel is absent, and treating it as such is what turns a transient outage
    into a duplicate publish (#1924).

    A release key can exist with an EMPTY file list after a delete, so presence
    of the key alone is not presence of a wheel.
    """
    url = PYPI_JSON_URL.format(package=package)
    fetch = opener or urllib.request.urlopen
    try:
        with fetch(url, timeout=timeout) as resp:  # type: ignore[operator]
            payload = json.load(resp)
        releases = payload.get("releases")
        if not isinstance(releases, dict):
            raise ValueError("PyPI payload carries no releases map")
        return bool(releases.get(str(version)))
    except (urllib.error.URLError, OSError, ValueError, TypeError, KeyError,
            AttributeError) as exc:
        _log.warning(
            "PyPI version-presence query failed; presence is UNKNOWN, not absent",
            extra={"package": package, "version": version, "reason": str(exc)},
        )
        return None


def github_release_exists(
    tag: str, repo: str, *, runner: Optional[Callable] = None, timeout: float = 15.0,
) -> Optional[bool]:
    """Whether a GitHub Release object exists for ``tag``.

    ``True``/``False`` when GitHub answered, ``None`` when it could not be asked.
    The distinction is load-bearing: "I could not check" is not "it is missing",
    and publishing on the strength of an unanswered question is how a duplicate
    is made.

    Deliberately the REST endpoint (``repos/{repo}/releases/tags/{tag}``) rather
    than ``gh release view``. REST and GraphQL are separate rate-limit buckets,
    and it was the GraphQL bucket that failed in the run this issue is about —
    ``gh release create`` died on "API rate limit already exceeded" while REST
    stood at 4823/5000, and the same operation over REST then succeeded on the
    first try (#1924).
    """
    import subprocess

    run = runner or subprocess.run
    try:
        proc = run(
            ["gh", "api", f"repos/{repo}/releases/tags/{tag}", "--jq", ".id"],
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, ValueError) as exc:
        _log.warning("gh release lookup could not run; presence is UNKNOWN",
                     extra={"tag": tag, "repo": repo, "reason": str(exc)})
        return None
    if proc.returncode == 0:
        return bool((proc.stdout or "").strip())
    stderr = (proc.stderr or "") + (proc.stdout or "")
    if "Not Found" in stderr or "404" in stderr:
        return False          # an answer: there is no release for this tag
    _log.warning("gh release lookup failed; presence is UNKNOWN, not absent",
                 extra={"tag": tag, "repo": repo, "stderr": stderr.strip()[:200]})
    return None


def resolve_release_base(git_tag: Optional[str], pypi_latest: Optional[str]) -> str:
    """The authoritative base version for the next release bump.

    Returns ``semver_max(git_tag, pypi_latest)`` — the greatest of the nearest git
    tag and the PyPI latest. This is the #1326 fix: basing the reconcile on the git
    tag alone regresses below the real published latest (the tag drifts via manual
    publishes, orphan tags, and the git-ignored store). Anchoring on
    ``max(pypi, tag)`` guarantees the base is ``>= pypi_latest``, so a subsequent
    :func:`bump` is strictly above what is already published. When PyPI is
    unreachable (``pypi_latest is None``) it falls back to the git tag. Raises
    :class:`VersionError` only if neither candidate is a parseable version.
    """
    base = semver_max(git_tag, pypi_latest)
    if base is None:
        raise VersionError(
            f"no resolvable release base (git_tag={git_tag!r}, pypi_latest={pypi_latest!r})"
        )
    return base


def current(conn: sqlite3.Connection) -> str:
    """The authoritative current version from the singleton release object.

    Raises :class:`VersionError` if the release object is absent (store predating
    migration v2) — callers wanting a non-raising default should use
    :func:`emit`.
    """
    obj = ObjectStore(conn).get(RELEASE_UID)
    if obj is None:
        raise VersionError(
            "no release object in the State Store (run `atdd state init` to migrate to v2)"
        )
    version = obj.data.get("version")
    if not version:
        raise VersionError("release object carries no version")
    return str(version)


def emit(conn: sqlite3.Connection) -> str:
    """The build-consumable version string, never raising.

    Returns :data:`LOCAL_FALLBACK_VERSION` when no release version is resolvable
    — the same contract as the build hook, so ``atdd state version emit`` and the
    packaging build agree.
    """
    try:
        return current(conn)
    except VersionError as exc:
        _log.info(
            "no release version resolvable; using local fallback",
            extra={"fallback": LOCAL_FALLBACK_VERSION, "reason": str(exc)},
        )
        return LOCAL_FALLBACK_VERSION


def next_from_change_class(conn: sqlite3.Connection, change_class: str) -> str:
    """The next version for a ``change_class`` bump applied to :func:`current` (no write)."""
    major, minor, patch = parse(current(conn))
    return _next(major, minor, patch, change_class)


#: Conventional-commit type header, e.g. ``feat(scope)!: subject`` — captures the
#: type token and an optional ``!`` breaking marker (#1172 design doc §3.1).
_CONVENTIONAL_HEADER = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\([^)]*\))?(?P<bang>!)?:")
#: A ``feat`` type is the only non-breaking MINOR; everything else is a PATCH.
_MINOR_TYPES = frozenset({"feat"})
#: A genuine Conventional-Commits breaking-change FOOTER — a ``BREAKING CHANGE:``
#: or ``BREAKING-CHANGE:`` token at the start of a line (optional leading
#: whitespace), terminated by a colon. Line-anchored (``re.MULTILINE``) so a mere
#: PROSE mention of the phrase mid-sentence does NOT escalate the class. This
#: closes the #1297 regression where the #1285/#1291 merge commit's own body
#: ("...breaking !/BREAKING CHANGE=MAJOR, else PATCH") misclassified a non-breaking
#: ``feat`` as MAJOR and bumped 3.151.0 -> 4.0.0 instead of 3.152.0.
_BREAKING_FOOTER = re.compile(r"^[ \t]*BREAKING[ -]CHANGE:", re.MULTILINE)


def change_class_for_commit(subject: str) -> str:
    """Derive the release change class from a conventional-commit message.

    Policy (mirrors the dead ``post-merge-lifecycle.yml`` bump step, now in core —
    #1172 design doc §3.1). The change-class is an *input* to :func:`bump`; this
    thin policy maps the merge commit's conventional-commit type onto it:

    - a ``!`` breaking marker (``type!:``) or a genuine ``BREAKING CHANGE:`` /
      ``BREAKING-CHANGE:`` *footer* (a line-anchored, colon-terminated token per the
      Conventional Commits spec — NOT a prose mention of the phrase) → ``MAJOR``;
    - a ``feat`` type → ``MINOR``;
    - ``fix`` / ``chore`` / ``docs`` / ``refactor`` / ``devops`` and any other or
      unrecognized type → ``PATCH`` (the conservative default).
    """
    text = subject or ""
    match = _CONVENTIONAL_HEADER.match(text.strip())
    if (match and match.group("bang")) or _BREAKING_FOOTER.search(text):
        return "MAJOR"
    if match and match.group("type").lower() in _MINOR_TYPES:
        return "MINOR"
    return "PATCH"


def set_version(conn: sqlite3.Connection, version: str) -> str:
    """Reconcile the store's authoritative current to ``version`` (no decision signal).

    Used by the release pipeline to seed the store's current from an
    already-published identity (e.g. the latest git tag) before a
    :func:`bump` decides the *next* version. Two effects, in order:

    1. **Authoritative state change** — upsert the release object's ``version``.
    2. **Audit trail** — append a ``version_bumped`` event recording the reconcile
       (``{from,to,change_class: "SET",pr: None}``).

    It deliberately enqueues **no** ``version_decided`` outbox message: reconciling
    the stored current from an already-published version is not a decision to
    publish — only :func:`bump` decides. Returns ``version``.
    """
    parse(version)  # validate a semver core; raises VersionError otherwise
    from_version = emit(conn)  # non-raising: real current or the local fallback
    ObjectStore(conn).upsert(RELEASE_UID, RELEASE_KIND, data={"version": version})
    EventStore(conn).append(
        VERSION_BUMPED_EVENT,
        object_uid=RELEASE_UID,
        payload={"from": from_version, "to": version, "change_class": "SET", "pr": None},
    )
    _log.info(
        "release version reconciled (set); no version_decided signal enqueued",
        extra={"from": from_version, "to": version},
    )
    return version


def bump(conn: sqlite3.Connection, change_class: str, *, pr: Optional[str] = None,
         provider: str = DEFAULT_PROVIDER) -> str:
    """Apply a version bump and emit the provider-neutral decision signal.

    Three effects, in order:

    1. **Authoritative state change** — upsert the release object's ``version``.
    2. **Audit trail** — append a ``version_bumped`` event (``{from,to,change_class,pr}``).
    3. **Neutral decision signal** — enqueue a ``version_decided`` outbox message
       carrying only ``{version, change_class}`` (#1172 design doc §2/§3). Core
       *decides* and stops here; the release extension drains this outbox to
       create the tag + publish + write the tag ref back. Core names no provider's
       publish mechanics: the operation + payload are neutral; only the outbox
       routing ``provider`` is a configured value (default :data:`DEFAULT_PROVIDER`).

    Returns the new version.
    """
    cls = change_class.upper()
    from_version = current(conn)
    to_version = next_from_change_class(conn, change_class)
    ObjectStore(conn).upsert(RELEASE_UID, RELEASE_KIND, data={"version": to_version})
    EventStore(conn).append(
        VERSION_BUMPED_EVENT,
        object_uid=RELEASE_UID,
        payload={"from": from_version, "to": to_version, "change_class": cls, "pr": pr},
    )
    outbox_id = SyncStore(conn).enqueue_outbox(
        provider, VERSION_DECIDED_OPERATION,
        {"version": to_version, "change_class": cls},
    )
    _log.info(
        "release version bumped; version_decided signal enqueued",
        extra={"from": from_version, "to": to_version, "change_class": cls,
            "pr": pr, "provider": provider, "outbox_id": outbox_id},
    )
    return to_version
