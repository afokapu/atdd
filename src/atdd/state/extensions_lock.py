""".atdd/extensions.lock — pin core's policies and every provider's digest (#1400 §10 rule 5).

> **Spec §10 rule 5.** ``.atdd/extensions.lock`` must lock core schema, lifecycle policy, merge
> policy, and provider digests.

The lock is what makes "a provider failure never blocks merge" a *safe* promise rather than a
reckless one. Core tolerates a mirror that breaks — but only because it can tell, before the
mirror runs, that the extension is still the one it agreed to run against. An unlocked extension
that drifts does not fail loudly; it mirrors *wrongly*, and quietly, into the projection everybody
reads. So the digest is checked first and the tolerance is granted second.

Three core digests, because a provider can be pinned against three different things and drift
away from any one of them independently:

``projection_schema_digest``
    The shape of a projection object (``commons:projection-object``, as core enforces it).
``lifecycle_policy_digest``
    The §6 evidence table — what a transition must carry to be legal.
``merge_policy_digest``
    The §7.1 field-ownership table — who may write what, and how a divergence merges.

Written **atomically or not at all**: the whole document is built and verified in memory, and a
single missing digest or a provider whose live ``digest()`` disagrees with its recorded entry
aborts before the file is opened. A half-written lock is worse than no lock — it looks pinned.

Deterministic by construction: sorted keys, sorted providers, no timestamp, no host path, no
secret. Two runs over the same inputs produce byte-identical output, which is what lets the lock
be committed and diffed rather than regenerated and ignored.

Dependency discipline: stdlib + ``pyyaml`` + ``atdd.state`` (never a provider).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import yaml

from atdd.state import evidence, ownership, projection
from atdd.state.provider_seam import ExtensionDigest, SyncProvider

_log = logging.getLogger(__name__)

#: Where the lock lives, relative to the Control Root.
LOCK_RELATIVE = Path(".atdd") / "extensions.lock"

#: ``commons:provider-extensions-lock``.
SCHEMA_VERSION = 1

#: The three core digests the contract makes ``required``. Named as data so a missing one is
#: reported by *name* rather than by a KeyError somebody has to decode.
CORE_DIGESTS: tuple = (
    "projection_schema_digest", "lifecycle_policy_digest", "merge_policy_digest",
)

#: Every key the ``core`` block carries.
CORE_KEYS: tuple = ("atdd_version", *CORE_DIGESTS)

DIGEST_PREFIX = "sha256:"


class LockError(ValueError):
    """The lock could not be built or does not verify. Nothing is written."""


class ExtensionDriftError(LockError):
    """A registered provider's live digest disagrees with the one the lock pinned.

    This is the failure the lock exists for: the extension changed under a checkout that believes
    it did not. Detected *before* the provider mirrors, never after.
    """


def _digest(payload: Any) -> str:
    """``sha256:<hex>`` over a canonical JSON rendering — sorted keys, no whitespace drift."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return DIGEST_PREFIX + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# The three core digests
# --------------------------------------------------------------------------- #
def projection_schema_shape() -> Dict[str, Any]:
    """The projection-object schema as core *enforces* it, in a hashable form.

    Derived from the validator's own constants rather than from the authored ``.schema.json``:
    a lock pinned to a file core does not read would pin the documentation, not the behaviour.
    """
    return {
        "fields": {
            name: sorted(
                type_.__name__ for type_ in
                (types if isinstance(types, tuple) else (types,))
            )
            for name, types in projection.FIELD_TYPES.items()
        },
        "required": sorted(projection.REQUIRED_FIELDS),
        "phases": list(projection.PHASES),
        "states": list(projection.STATES),
    }


def projection_schema_digest() -> str:
    return _digest(projection_schema_shape())


def lifecycle_policy_digest() -> str:
    """The §6 evidence table — the legal-transition gate's whole policy."""
    return _digest(evidence.EVIDENCE_POLICY)


def merge_policy_digest(root: Optional[Path] = None) -> str:
    """The §7.1 ownership table: the repo's committed policy, or the one core ships.

    The same fallback the merge-authority run makes, and for the same reason: a checkout with no
    committed policy is governed by the shipped table, never by nothing (spec §7.1).
    """
    if root is not None:
        try:
            return _digest(ownership.load_policy(Path(root)).as_document())
        except ownership.PolicyNotFound as exc:
            _log.info(
                "no committed field-ownership policy; the lock pins the shipped table",
                extra={"root": str(root), "expected": str(exc.path)},
            )
    return _digest(ownership.default_policy().as_document())


def core_version() -> str:
    """The running core's version — what a provider declares itself compatible with."""
    from atdd import __version__

    return str(__version__)


def core_block(root: Optional[Path] = None, *, atdd_version: Optional[str] = None) -> Dict[str, Any]:
    """The ``core`` block: the version, and the three policies a provider is pinned against."""
    return {
        "atdd_version": atdd_version or core_version(),
        "projection_schema_digest": projection_schema_digest(),
        "lifecycle_policy_digest": lifecycle_policy_digest(),
        "merge_policy_digest": merge_policy_digest(root),
    }


# --------------------------------------------------------------------------- #
# Building the lock (E002)
# --------------------------------------------------------------------------- #
def provider_entries(providers: Mapping[str, SyncProvider]) -> Dict[str, Dict[str, str]]:
    """Each registered provider's ``{version, digest}``, keyed by name.

    A provider whose ``digest()`` is unusable is a *fault in the lock*, not an alarm to shrug at:
    the lock is the one place a provider's failure DOES stop the line, because an extension that
    cannot say what it is cannot be pinned, and an unpinned extension may not mirror.
    """
    entries: Dict[str, Dict[str, str]] = {}
    for name in sorted(providers):
        try:
            stamp = providers[name].digest()
        except Exception as exc:  # noqa: BLE001 - reported as a lock fault, with the provider named
            raise LockError(
                f"provider {name!r} could not produce a digest ({exc}); an extension that cannot "
                "be pinned may not mirror"
            ) from exc
        entries[name] = _entry(name, stamp)
    return entries


def _entry(name: str, stamp: Any) -> Dict[str, str]:
    version = getattr(stamp, "version", None)
    digest = getattr(stamp, "digest", None)
    if not isinstance(version, str) or not isinstance(digest, str):
        raise LockError(
            f"provider {name!r} returned {stamp!r}, not an ExtensionDigest(name, version, digest)"
        )
    if not digest.startswith(DIGEST_PREFIX) or len(digest) != len(DIGEST_PREFIX) + 64:
        raise LockError(
            f"provider {name!r} digest {digest!r} is not 'sha256:<64 hex>' "
            "(commons:provider-extensions-lock)"
        )
    return {"version": version, "digest": digest}


def build_lock(
    providers: Optional[Mapping[str, SyncProvider]] = None,
    *,
    root: Optional[Path] = None,
    atdd_version: Optional[str] = None,
) -> Dict[str, Any]:
    """The whole lock document. With zero providers the ``providers`` block is present and empty.

    Present and empty, not absent: "this checkout has no extensions" is a fact the lock states,
    and a reader must be able to tell it apart from "somebody forgot to write the block".
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "core": core_block(root, atdd_version=atdd_version),
        "providers": provider_entries(providers or {}),
    }


def canonical_bytes(document: Mapping[str, Any]) -> bytes:
    """The lock's bytes. Deterministic: sorted keys, block style, no aliases, UTF-8."""
    return yaml.safe_dump(
        _plain(document), sort_keys=True, default_flow_style=False, allow_unicode=True,
    ).encode("utf-8")


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


# --------------------------------------------------------------------------- #
# Verification (E002) — before any write, and before any mirror
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LockReport:
    """The verdict on a lock document."""

    problems: List[str] = field(default_factory=list)
    providers: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def render(self) -> str:
        if self.ok:
            return (
                f"extensions.lock verifies: schema_version {SCHEMA_VERSION}, the three core policy "
                f"digests, {len(self.providers)} provider(s) {self.providers}"
            )
        return "\n".join([
            f"extensions.lock does not verify ({len(self.problems)} problem(s)):",
            *(f"  {problem}" for problem in self.problems),
        ])


def verify(
    document: Mapping[str, Any],
    providers: Optional[Mapping[str, SyncProvider]] = None,
    *,
    root: Optional[Path] = None,
) -> LockReport:
    """Check a lock: shape, the three core digests, and every provider's live digest.

    Collects **every** problem rather than raising on the first: an operator regenerating a lock
    wants the whole list, not a queue of one-at-a-time refusals.
    """
    problems: List[str] = []
    if not isinstance(document, Mapping):
        return LockReport(problems=["the lock is not a mapping (commons:provider-extensions-lock)"])

    if document.get("schema_version") != SCHEMA_VERSION:
        problems.append(
            f"schema_version is {document.get('schema_version')!r}, not {SCHEMA_VERSION}"
        )

    core = document.get("core")
    if not isinstance(core, Mapping):
        problems.append("the 'core' block is missing; the lock pins no core policy at all")
    else:
        for key in CORE_KEYS:
            if not core.get(key):
                problems.append(f"core.{key} is missing (spec §10 rule 5 requires it)")
        expected = core_block(root, atdd_version=core.get("atdd_version"))
        for key in CORE_DIGESTS:
            if core.get(key) and core[key] != expected[key]:
                problems.append(
                    f"core.{key} pins {core[key]}, but this checkout computes {expected[key]} — "
                    "the policy changed under the lock"
                )

    recorded = document.get("providers")
    if not isinstance(recorded, Mapping):
        problems.append("the 'providers' block is missing; with no extensions it is present and empty")
        recorded = {}

    live = providers or {}
    for name in sorted(set(recorded) | set(live)):
        problems.extend(_provider_problems(name, recorded.get(name), live.get(name)))

    report = LockReport(problems=problems, providers=sorted(recorded))
    if not report.ok:
        _log.warning("extensions.lock did not verify", extra={"problems": problems})
    return report


def _provider_problems(
    name: str, recorded: Any, provider: Optional[SyncProvider],
) -> List[str]:
    """Every disagreement between what the lock pinned and what the provider now is."""
    if recorded is None:
        return [
            f"provider {name!r} is registered but not pinned in the lock; an unpinned extension "
            "may not mirror"
        ]
    if not isinstance(recorded, Mapping):
        return [f"provider {name!r} entry is {recorded!r}, not a mapping"]
    problems = [
        f"providers.{name}.{key} is missing" for key in ("version", "digest")
        if not recorded.get(key)
    ]
    if provider is None or problems:
        return problems
    try:
        stamp = provider.digest()
        entry = _entry(name, stamp)
    except LockError as exc:
        # Logged as well as reported: the operator reads the report, and whoever reads the CI run's
        # log next week reads this.
        _log.warning(
            "a registered provider's digest could not be verified against the lock",
            extra={"provider": name, "error": str(exc), "type": type(exc).__name__},
        )
        return [f"provider {name!r}: {exc}"]
    except Exception as exc:  # noqa: BLE001 - a provider that cannot self-describe is drift
        _log.warning(
            "a registered provider could not produce a digest; it cannot be pinned",
            extra={"provider": name, "error": str(exc), "type": type(exc).__name__},
        )
        return [f"provider {name!r} could not produce a digest ({exc})"]
    if entry["digest"] != recorded["digest"]:
        problems.append(
            f"EXTENSION DRIFT: provider {name!r} now digests {entry['digest']}, but the lock pins "
            f"{recorded['digest']} — the extension changed under a checkout that thinks it did not"
        )
    if entry["version"] != recorded["version"]:
        problems.append(
            f"EXTENSION DRIFT: provider {name!r} is version {entry['version']}, but the lock pins "
            f"{recorded['version']}"
        )
    return problems


# --------------------------------------------------------------------------- #
# Reading and writing
# --------------------------------------------------------------------------- #
def lock_path(root: Path) -> Path:
    return Path(root) / LOCK_RELATIVE


def read_lock(root: Path) -> Dict[str, Any]:
    """The committed lock. A missing file is a refusal, not an empty lock."""
    path = lock_path(root)
    if not path.is_file():
        raise LockError(
            f"no extensions lock at {path}; core's schema and policies are unpinned and no "
            "extension can be verified against them (spec §10 rule 5)"
        )
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise LockError(f"{path} is not a commons:provider-extensions-lock document")
    return dict(document)


def write_lock(
    root: Path,
    providers: Optional[Mapping[str, SyncProvider]] = None,
    *,
    atdd_version: Optional[str] = None,
) -> Path:
    """Build, verify, and only then write ``.atdd/extensions.lock``.

    Verified before the file is opened: a lock that would not pass its own check must never reach
    the disk, because everything downstream — including core's willingness to tolerate a failing
    mirror — is granted on the strength of it.
    """
    document = build_lock(providers, root=root, atdd_version=atdd_version)
    report = verify(document, providers, root=root)
    if not report.ok:
        raise LockError(
            f"refusing to write a lock that does not verify:\n{report.render()}"
        )
    path = lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(document))
    return path


def verify_repo(
    root: Path, providers: Optional[Mapping[str, SyncProvider]] = None,
) -> LockReport:
    """Verify the lock a checkout committed against the providers it actually has."""
    return verify(read_lock(root), providers, root=Path(root))
