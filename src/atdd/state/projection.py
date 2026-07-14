"""The committed projection — shared source of truth (#1400 project-shared-state).

The scoped-truth rule (spec §1): the local SQLite store is the *private authoring
workspace*; the committed, deterministic per-uid projection under
``.atdd/state/projection/<uid>.yaml`` is the *shared* source of truth that peers
and CI read. This module is the projection spine (milestone M1):

- :func:`project`            — store → byte-identical canonical per-uid YAML (I1).
- :func:`hydrate`            — committed projection at HEAD → store, zero providers.
- :func:`projection_digest`  — a stable digest over the canonical bytes.
- :func:`check_canonicality` — the honest CI guarantee (spec §4):
  ``project(hydrate(committed projection)) == committed projection``, byte-for-byte.

Determinism (I1) is enforced *before* any byte is written: a document carrying a
wall-clock timestamp or an absolute host path is refused, and every unordered
collection reaching the serializer is emitted in a total, content-derived order.
The three known leaks — timestamps, host paths, iteration order — each have a
guard here; nothing else may reach a projection file.

The document shape is the ``commons:projection-object`` contract
(``contracts/commons/projection-object.schema.json``). The authored schema is the
source of truth for the shape; the constants below are its executable form, and
``state/tests/test_projection_schema_matches_contract.py`` fails if the two drift.
The schema is NOT vendored under ``state/`` — that layer holds operational data
and storage APIs only, never authored definitions (``coder.state-store``
``.operational-vs-definition-sot``).

Dependency discipline: stdlib + ``pyyaml`` + ``atdd.state`` only. In particular it
imports **no** provider and never consults ``external_refs`` for a lifecycle
decision (I7, spec §8.2 rule 5).
"""
from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import yaml

from atdd.state.identity import UID_RE, is_uid
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.store import Object, StateStore

_log = logging.getLogger(__name__)

#: Where the committed projection lives, relative to the Control Root.
PROJECTION_RELATIVE = Path(".atdd") / "state" / "projection"

#: One document per object; the uid — and only the uid — names the file.
PROJECTION_SUFFIX = ".yaml"

#: Lifecycle phases a *committed* projection may carry. COMPLETE is deliberately
#: absent: it is DERIVED from merge-to-main (spec §18 decision 1), so a committed
#: projection asserting phase=COMPLETE is invalid, not merely stale.
PHASES: Tuple[str, ...] = (
    "INIT", "PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR", "BLOCKED", "OBSOLETE",
)

#: Lifecycle phases a store object may carry that are NOT projected. ``COMPLETE`` is
#: derived from merge-to-main (spec §18 decision 1): it has no legal projection
#: document, so the projector passes over such objects rather than refusing them (see
#: :func:`build_documents`). The store keeps the record; git keeps the completion.
ARCHIVED_PHASES: Tuple[str, ...] = ("COMPLETE",)

#: Retirement is a tombstone record, never a file deletion (spec §10 rule 3).
STATES: Tuple[str, ...] = ("ACTIVE", "TOMBSTONED")

#: The default lifecycle state of a live object.
STATE_ACTIVE = "ACTIVE"
STATE_TOMBSTONED = "TOMBSTONED"

#: Every field the contract admits (``additionalProperties: false``), with the
#: type(s) it may take. Anything outside this table is refused.
FIELD_TYPES: Dict[str, Any] = {
    "uid": str,
    "slug": str,
    "title": str,
    "body": str,
    "phase": str,
    "state": str,
    "owner_actor": str,
    "last_lifecycle_actor": (str, type(None)),
    "train": (str, type(None)),
    "wmbts": list,
    "extension_digests": dict,
    "external_refs": dict,
    "tombstone": dict,
}

#: Contract ``required``.
REQUIRED_FIELDS: Tuple[str, ...] = ("uid", "phase", "state", "owner_actor")

#: A ``sha256:<hex>`` stamp, the one digest form the contract accepts.
DIGEST_PREFIX = "sha256:"


class ProjectionError(ValueError):
    """Base class for every refusal raised on the projection path."""


class NondeterministicProjectionError(ProjectionError):
    """A document would carry a determinism leak; no file is written (C001).

    Carries the offending ``field`` so the operator is told *what* to remove,
    not merely that the projection was refused.
    """

    def __init__(self, field_path: str, reason: str, *, uid: Optional[str] = None) -> None:
        self.field_path = field_path
        self.reason = reason
        self.uid = uid
        where = f"{uid} " if uid else ""
        super().__init__(
            f"nondeterministic projection content {where}at field {field_path!r}: {reason}"
        )


class ProjectionSchemaError(ProjectionError):
    """A document does not conform to ``commons:projection-object``."""


# --------------------------------------------------------------------------- #
# Determinism guard (C001) — refuse the three known leaks before any write
# --------------------------------------------------------------------------- #
#: Field names that carry a wall-clock reading by convention. Any ``*_at`` key is
#: caught by the suffix rule as well; these are the ones that do not end in ``_at``.
_TIMESTAMP_KEYS = frozenset({"timestamp", "now", "date", "datetime", "mtime", "ctime"})

#: An ISO-8601 wall-clock reading anywhere inside a string value.
_TIMESTAMP_VALUE_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")

#: The per-host filesystem namespaces. A path rooted in one of these differs
#: between developers, between CI runners, and between checkouts of the same repo,
#: so it can never appear in a shared artifact.
_HOST_PATH_RE = re.compile(
    r"(?:/Users/|/home/|/root/|/private/var/|/var/folders/|/var/tmp/|/tmp/|[A-Za-z]:\\)"
)

#: The free-text fields, exempt from the *value* scan.
#:
#: I1 is about content the **projector** generates. A path or a date inside the
#: issue body is not generated — it is *preserved*: the projector copies what a
#: human wrote, byte for byte, and copies the same bytes on every host and every
#: run. Prose that happens to quote ``/Users/alec/…`` or ``2026-07-11`` is
#: therefore deterministic by preservation, and refusing it would refuse a
#: perfectly legal issue body while catching nothing (spec §2.2 I1: "no timestamps,
#: host paths, or unstable ordering" names the three ways *machine-injected*
#: volatility reaches a shared artifact).
#:
#: The scan is narrowed to the generated and structured fields — where a leak means
#: the projector reached for the wall clock or the local filesystem, which is the
#: fault I1 exists to catch. The *key*-name rule (below) still applies to every
#: field, free-text included: a field named ``body_at`` is a timestamp field
#: whatever it holds.
FREE_TEXT_FIELDS: frozenset = frozenset({"body"})


def _scalar_fault(value: str) -> Optional[str]:
    """The determinism fault a string *value* carries, or ``None`` if it is clean."""
    if _TIMESTAMP_VALUE_RE.search(value):
        return "carries a wall-clock timestamp"
    if _HOST_PATH_RE.search(value):
        return "carries an absolute host path"
    return None


def _key_fault(key: str) -> Optional[str]:
    """The determinism fault a mapping *key* carries, or ``None`` if it is clean."""
    lowered = key.lower()
    if lowered.endswith("_at") or lowered in _TIMESTAMP_KEYS:
        return "is a wall-clock timestamp field"
    return None


def _walk_for_faults(node: Any, path: str, faults: List[Tuple[str, str]]) -> None:
    """Collect ``(field_path, reason)`` for every determinism leak under ``node``.

    A top-level free-text field has its *value* skipped (see :data:`FREE_TEXT_FIELDS`);
    its key is still judged, and a field of the same name nested inside a structured
    field — ``external_refs.body``, say — is machine-written and is scanned.
    """
    if isinstance(node, Mapping):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            reason = _key_fault(str(key))
            if reason is not None:
                faults.append((child, reason))
            if child in FREE_TEXT_FIELDS:
                continue
            _walk_for_faults(value, child, faults)
        return
    if isinstance(node, (list, tuple, set, frozenset)):
        for index, value in enumerate(node):
            _walk_for_faults(value, f"{path}[{index}]", faults)
        return
    if isinstance(node, str):
        reason = _scalar_fault(node)
        if reason is not None:
            faults.append((path, reason))


def assert_deterministic(document: Mapping[str, Any], *, uid: Optional[str] = None) -> None:
    """Refuse ``document`` if a *generated* field carries a timestamp or host path (I1, C001).

    Raises :class:`NondeterministicProjectionError` naming the first offending
    field. Callers run this over *every* document before writing *any* file, so a
    single leak leaves the whole projection unwritten rather than half-applied.

    The scan covers the projector-generated and structured fields. The free-text
    body is exempt from the value scan: its content is authored, not generated, so
    it is deterministic by preservation (see :data:`FREE_TEXT_FIELDS`).
    """
    faults: List[Tuple[str, str]] = []
    _walk_for_faults(document, "", faults)
    if not faults:
        return
    field_path, reason = faults[0]
    _log.warning(
        "projection refused: nondeterministic content",
        extra={"uid": uid, "field": field_path, "reason": reason, "faults": len(faults)},
    )
    raise NondeterministicProjectionError(field_path, reason, uid=uid)


# --------------------------------------------------------------------------- #
# Canonical bytes (I1) — total, content-derived order; no iteration-order leak
# --------------------------------------------------------------------------- #
def _order_key(value: Any) -> str:
    """A total, *content-derived* sort key — never insertion order, never hash order."""
    return json.dumps(value, sort_keys=True, default=str)


def canonicalize(value: Any) -> Any:
    """Rewrite ``value`` into its canonical form: sets and sequences sorted by content.

    Sets and dicts have no inherent order, and CPython's iteration order for a set
    of strings varies with ``PYTHONHASHSEED``. Sorting by the JSON rendering of each
    element makes the emitted order a function of the *content* alone, so the same
    logical store yields the same bytes on every host and every run.
    """
    if isinstance(value, Mapping):
        return {str(k): canonicalize(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (set, frozenset, list, tuple)):
        return sorted((canonicalize(v) for v in value), key=_order_key)
    return value


def canonical_bytes(document: Mapping[str, Any]) -> bytes:
    """The canonical UTF-8 bytes of ``document`` — the unit the digest and CI compare.

    Keys are emitted in a fixed (sorted) order, sequences in content-derived order,
    block style throughout, and never line-wrapped (a wrap point would otherwise
    depend on nothing but the dumper's default width).
    """
    text = yaml.safe_dump(
        canonicalize(dict(document)),
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
        width=1 << 30,
    )
    return text.encode("utf-8")


# --------------------------------------------------------------------------- #
# Schema (commons:projection-object)
# --------------------------------------------------------------------------- #
def _validate_enum(document: Mapping[str, Any]) -> List[str]:
    problems: List[str] = []
    if not is_uid(document.get("uid")):
        problems.append(f"uid {document.get('uid')!r} does not match {UID_RE.pattern}")
    if document.get("phase") not in PHASES:
        problems.append(
            f"phase {document.get('phase')!r} is not one of {list(PHASES)} "
            "(COMPLETE is derived from merge-to-main, never committed)"
        )
    if document.get("state") not in STATES:
        problems.append(f"state {document.get('state')!r} is not one of {list(STATES)}")
    return problems


def validate_document(document: Mapping[str, Any]) -> None:
    """Refuse ``document`` unless it conforms to ``commons:projection-object``.

    Checks the contract's ``required``, its ``additionalProperties: false``, the
    declared types, and the three constrained vocabularies (uid pattern, phase and
    state enums). Raises :class:`ProjectionSchemaError` listing every problem — an
    operator fixing a hand-edited file wants them all at once, not one per run.
    """
    problems: List[str] = [
        f"missing required field {name!r}"
        for name in REQUIRED_FIELDS
        if name not in document
    ]
    for key, value in document.items():
        expected = FIELD_TYPES.get(key)
        if expected is None:
            problems.append(f"unknown field {key!r} (the contract forbids extra properties)")
        elif not isinstance(value, expected):
            problems.append(f"field {key!r} has type {type(value).__name__}, expected {expected}")
    problems.extend(_validate_enum(document))
    if problems:
        raise ProjectionSchemaError(
            f"projection document {document.get('uid', '<no uid>')} is invalid: "
            + "; ".join(problems)
        )


# --------------------------------------------------------------------------- #
# Document ↔ store object
# --------------------------------------------------------------------------- #
def build_document(obj: Object) -> Dict[str, Any]:
    """The projection document for a stored object — a pure, total mapping.

    The ``objects.state`` column is the lifecycle *phase* (the store's long-standing
    convention); every other projection field lives in the object's ``data`` bag and
    is carried through verbatim, so nothing is silently dropped on the way out. An
    object that never recorded a retirement is ``ACTIVE``.
    """
    document: Dict[str, Any] = dict(obj.data)
    document["uid"] = obj.uid
    document["phase"] = obj.state
    document.setdefault("state", STATE_ACTIVE)
    return document


def document_to_object(document: Mapping[str, Any]) -> Tuple[str, Optional[str], Dict[str, Any]]:
    """The inverse of :func:`build_document`: ``(uid, phase, data)`` for the store.

    ``external_refs`` rides along inside ``data`` verbatim. It is *carried*, never
    *consulted* — no phase, no transition, and no lifecycle decision anywhere in
    core reads it (I7).
    """
    data = {k: v for k, v in document.items() if k not in ("uid", "phase")}
    return str(document["uid"]), document.get("phase"), data


# --------------------------------------------------------------------------- #
# project(store) → canonical per-uid YAML
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProjectionResult:
    """What a :func:`project` run wrote."""

    out_dir: Path
    #: uid → the file written for it.
    files: Dict[str, Path] = field(default_factory=dict)
    #: The digest over the canonical bytes of the whole projection set.
    digest: str = ""


def build_documents(store: StateStore) -> Dict[str, Dict[str, Any]]:
    """Every **projectable** object as a validated document, keyed by uid.

    Refuses the whole set if any document leaks nondeterministic content or breaks
    the contract — so a bad object cannot leave a half-written projection behind.

    A ``COMPLETE`` object is **archived, not refused** (:data:`ARCHIVED_PHASES`).
    ``COMPLETE`` is derived from merge-to-main (spec §18 decision 1), so a completed
    work item has no legal projection document — and every real store holds them.
    Refusing them would mean no real repo could ever be projected; fabricating a
    phase for them ("it was probably SMOKE") would be the lossy write the migration
    guard exists to prevent. So the projector passes over them: their completion
    lives in the merge commit that caused it, and their record lives in the store.
    A *document* still may not claim ``COMPLETE`` — :func:`validate_document`
    refuses that, and should.
    """
    documents: Dict[str, Dict[str, Any]] = {}
    for obj in store.objects.list(kind=WORK_ITEM_KIND):
        if obj.state in ARCHIVED_PHASES:
            continue
        document = build_document(obj)
        assert_deterministic(document, uid=obj.uid)
        validate_document(document)
        documents[obj.uid] = document
    return documents


def object_digest(document: Mapping[str, Any]) -> str:
    """The ``sha256:<hex>`` digest over *one* object's canonical bytes.

    This is the stamp an ``ATDD-Projection-Digest`` trailer carries: trailers are
    grouped per object (spec §5 rule 6), so the digest they pin must be per object too.
    """
    return DIGEST_PREFIX + hashlib.sha256(canonical_bytes(document)).hexdigest()


def digest_documents(documents: Mapping[str, Mapping[str, Any]]) -> str:
    """The ``sha256:<hex>`` digest over the canonical bytes of a document set."""
    hasher = hashlib.sha256()
    for uid in sorted(documents):
        hasher.update(uid.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(canonical_bytes(documents[uid]))
        hasher.update(b"\0")
    return DIGEST_PREFIX + hasher.hexdigest()


def project(store: StateStore, out_dir: Path) -> ProjectionResult:
    """Write the canonical per-uid projection for ``store`` into ``out_dir`` (I1).

    Every document is built and *fully* validated before the first byte is written,
    so a determinism leak or a schema break leaves ``out_dir`` untouched. The same
    logical store yields byte-identical files on any host, in any checkout, on any
    run — the filename is the uid and nothing else.
    """
    documents = build_documents(store)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files: Dict[str, Path] = {}
    for uid in sorted(documents):
        path = out_dir / f"{uid}{PROJECTION_SUFFIX}"
        path.write_bytes(canonical_bytes(documents[uid]))
        files[uid] = path
    _log.info(
        "projection written",
        extra={"out_dir": str(out_dir), "objects": len(files)},
    )
    return ProjectionResult(out_dir=out_dir, files=files, digest=digest_documents(documents))


# --------------------------------------------------------------------------- #
# hydrate(projection) → store
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HydrateResult:
    """What a :func:`hydrate` run rebuilt."""

    hydrated: int
    uids: List[str] = field(default_factory=list)


def read_projection(projection_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Read and validate every ``<uid>.yaml`` under ``projection_dir``, keyed by uid.

    The filename is identity: a document whose ``uid`` disagrees with the file it
    was read from is a corrupted projection, not a rename, and is refused.
    """
    documents: Dict[str, Dict[str, Any]] = {}
    projection_dir = Path(projection_dir)
    if not projection_dir.is_dir():
        return documents
    for path in sorted(projection_dir.glob(f"*{PROJECTION_SUFFIX}"), key=lambda p: p.name):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ProjectionSchemaError(f"{path.name}: not a YAML mapping")
        validate_document(document)
        expected = path.name[: -len(PROJECTION_SUFFIX)]
        if document["uid"] != expected:
            raise ProjectionSchemaError(
                f"{path.name}: uid {document['uid']!r} does not name its file "
                "(the uid alone names the projection file)"
            )
        documents[document["uid"]] = document
    return documents


def hydrate(projection_dir: Path, store: StateStore) -> HydrateResult:
    """Rebuild the public store objects from the committed projection (E002).

    Runs with **zero** sync providers registered and against no committed SQLite
    store: the committed YAML at HEAD is the only input. This is the read half of
    the CI guarantee — CI hydrates what the branch committed, then re-projects it.
    """
    documents = read_projection(projection_dir)
    for uid in sorted(documents):
        obj_uid, phase, data = document_to_object(documents[uid])
        store.objects.upsert(  # noqa: N+1 — one upsert per projected object, not a query loop
            obj_uid, WORK_ITEM_KIND, state=phase, data=data,
        )
    _log.info(
        "projection hydrated",
        extra={"projection_dir": str(projection_dir), "objects": len(documents)},
    )
    return HydrateResult(hydrated=len(documents), uids=sorted(documents))


# --------------------------------------------------------------------------- #
# Digest + canonicality (C002) — the honest CI guarantee
# --------------------------------------------------------------------------- #
def projection_digest(projection_dir: Path) -> str:
    """The ``sha256:<hex>`` digest over the *committed* bytes of a projection directory.

    Taken over the bytes on disk (not a re-serialization), so a hand-edit moves the
    digest. Filenames are folded in too: adding or removing an object changes the
    stamp even when no surviving document changed.
    """
    hasher = hashlib.sha256()
    projection_dir = Path(projection_dir)
    paths = sorted(projection_dir.glob(f"*{PROJECTION_SUFFIX}"), key=lambda p: p.name)
    for path in paths:
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return DIGEST_PREFIX + hasher.hexdigest()


@dataclass(frozen=True)
class Mismatch:
    """One committed file whose bytes are not the canonical output of the round-trip."""

    filename: str
    diff: str


@dataclass(frozen=True)
class CanonicalityReport:
    """The outcome of ``project(hydrate(projection)) == projection``."""

    checked: int
    mismatches: List[Mismatch] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatches

    def render(self) -> str:
        """An operator-facing report naming each offending file with its diff."""
        if self.ok:
            return f"projection is canonical ({self.checked} object(s))"
        lines = [f"projection is NOT canonical ({len(self.mismatches)}/{self.checked} file(s)):"]
        for mismatch in self.mismatches:
            lines.append(f"  - {mismatch.filename}")
            lines.extend(f"      {line}" for line in mismatch.diff.splitlines())
        return "\n".join(lines)


def _diff(filename: str, committed: bytes, canonical: bytes) -> str:
    return "".join(
        difflib.unified_diff(
            committed.decode("utf-8", "replace").splitlines(keepends=True),
            canonical.decode("utf-8", "replace").splitlines(keepends=True),
            fromfile=f"committed/{filename}",
            tofile=f"canonical/{filename}",
        )
    )


def _read_bytes(projection_dir: Path) -> Dict[str, bytes]:
    """Every ``<uid>.yaml`` under ``projection_dir`` as raw bytes, keyed by filename."""
    return {
        path.name: path.read_bytes()
        for path in sorted(Path(projection_dir).glob(f"*{PROJECTION_SUFFIX}"), key=lambda p: p.name)
    }


def _mismatches(expected: Mapping[str, bytes], actual: Mapping[str, bytes]) -> List[Mismatch]:
    """Every filename whose bytes differ, each with a unified diff naming the file."""
    return [
        Mismatch(filename=name, diff=_diff(name, blob, actual.get(name, b"")))
        for name, blob in sorted(expected.items())
        if actual.get(name) != blob
    ]


def compare_projections(expected_dir: Path, actual_dir: Path) -> List[Mismatch]:
    """Byte-compare two projection directories (the golden-file check, E003).

    A golden fixture pins the canonical bytes; this reports every file that drifted
    from it, with a diff naming the offending file — so an unintended byte change
    fails loudly instead of drifting silently into a commit.
    """
    return _mismatches(_read_bytes(expected_dir), _read_bytes(actual_dir))


def check_canonicality(projection_dir: Path) -> CanonicalityReport:
    """Prove ``project(hydrate(projection)) == projection``, byte-for-byte (C002).

    This is the *only* guarantee CI can honestly make: it cannot read a gitignored
    developer store, so it takes the round-trip over the committed projection alone.
    The store used here is in-memory — no developer SQLite is touched — and no
    provider is registered or consulted, so the check also holds against a bare git
    remote with no GitHub API reachable.
    """
    projection_dir = Path(projection_dir)
    committed = _read_bytes(projection_dir)
    with memory_store() as store, tempfile.TemporaryDirectory() as tmp:
        hydrate(projection_dir, store)
        result = project(store, Path(tmp))
        canonical = {path.name: path.read_bytes() for path in result.files.values()}

    mismatches = _mismatches(committed, canonical)
    if mismatches:
        _log.warning(
            "projection canonicality check failed",
            extra={"projection_dir": str(projection_dir),
                "mismatches": [m.filename for m in mismatches]},
        )
    return CanonicalityReport(checked=len(committed), mismatches=mismatches)


class memory_store:  # noqa: N801 — a context-manager helper, used as `with memory_store()`
    """An ephemeral, migrated State Store held entirely in memory.

    The canonicality check must touch no developer SQLite (spec §4), so it hydrates
    into RAM and throws the connection away. Shadow runs on the same terms and for the
    same reason, so it uses this one rather than keeping a second copy of it.
    """

    def __enter__(self) -> StateStore:
        from atdd.state.db import apply_migrations  # local: keeps the import surface small

        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        apply_migrations(self._conn)
        return StateStore(self._conn)

    def __exit__(self, *_exc: Any) -> None:
        self._conn.close()
