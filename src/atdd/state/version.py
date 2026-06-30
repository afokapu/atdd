"""Release version as a State Store concern (#1172).

The State Store is the **local source of truth** for the release version. The
singleton ``release`` object (uid=``release``, seeded by migration v2) carries
the authoritative current value in ``data.version``; every bump records a
``version_bumped`` event so the history is auditable:

- :func:`current`               — the authoritative current version string.
- :func:`next_from_change_class` — the next version for a PATCH/MINOR/MAJOR bump
  (no write).
- :func:`bump`                  — apply a bump: write the object + append the
  event; returns the new version.
- :func:`publish_release`       — record the publication intent: an external_ref
  for the git tag + an outbox row the GitHub extension drains to tag + publish.

Change-class semantics match ``CLAUDE.md::release.change_class``:
``PATCH`` (bug/docs/refactor), ``MINOR`` (new feature, non-breaking), ``MAJOR``
(breaking change). Dependency discipline: stdlib + ``atdd.state`` only — NO
``atdd.coach`` import (#1220 boundary).
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Optional, Tuple

from atdd.state.projections import RELEASE_UID, VERSION_BUMPED_EVENT
from atdd.state.store import EventStore, ExternalRefStore, ObjectStore, SyncStore

_log = logging.getLogger(__name__)

RELEASE_KIND = "release"
#: The deterministic build-consumable fallback when no release version exists in
#: the store (mirrors the build hook's no-store fallback — see
#: ``build_meta_shim``). PEP 440 local version segment.
LOCAL_FALLBACK_VERSION = "0.0.0+local"

#: Publication routing (#1172 step 5): the GitHub extension drains this outbox.
PUBLISH_PROVIDER = "github"
PUBLISH_OPERATION = "tag_and_publish"
PUBLISH_REF_KIND = "tag"

_CHANGE_CLASSES = ("PATCH", "MINOR", "MAJOR")


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


def bump(conn: sqlite3.Connection, change_class: str, *, pr: Optional[str] = None) -> str:
    """Apply a version bump: write the release object and append a ``version_bumped`` event.

    Returns the new version. The object write is the authoritative state change;
    the event is the audit trail (``{from,to,change_class,pr}``).
    """
    from_version = current(conn)
    to_version = next_from_change_class(conn, change_class)
    ObjectStore(conn).upsert(RELEASE_UID, RELEASE_KIND, data={"version": to_version})
    EventStore(conn).append(
        VERSION_BUMPED_EVENT,
        object_uid=RELEASE_UID,
        payload={"from": from_version, "to": to_version,
                 "change_class": change_class.upper(), "pr": pr},
    )
    _log.info(
        "release version bumped",
        extra={"from": from_version, "to": to_version,
               "change_class": change_class.upper(), "pr": pr},
    )
    return to_version


def publish_release(conn: sqlite3.Connection, version: Optional[str] = None) -> int:
    """Record publication intent for ``version`` (default: :func:`current`).

    Links the git tag as an external_ref and enqueues a ``tag_and_publish`` outbox
    row. Core *decides*; the GitHub extension's release-worker drains the outbox to
    create the tag + publish to PyPI (the publication side effect lives in the
    provider extension, not core). Returns the outbox row id.
    """
    version = version or current(conn)
    tag = f"v{version}"
    ExternalRefStore(conn).link(RELEASE_UID, PUBLISH_PROVIDER, PUBLISH_REF_KIND, tag)
    outbox_id = SyncStore(conn).enqueue_outbox(
        PUBLISH_PROVIDER, PUBLISH_OPERATION, {"version": version, "tag": tag}
    )
    _log.info(
        "release publication enqueued",
        extra={"version": version, "tag": tag, "outbox_id": outbox_id},
    )
    return outbox_id
