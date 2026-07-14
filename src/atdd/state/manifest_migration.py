"""Legacy manifest → committed projection (#1400 migrate-projection-authority, CORE-031).

The one-way door. ``.atdd/manifest.yaml`` is a hand-editable ledger keyed by a **mutable slug**;
``.atdd/state/projection/<uid>.yaml`` is a derived, canonical document keyed by an **immutable
uid** (spec §10 rule 1). This module walks a repo across that gap: it reads the legacy manifest,
hydrates the store, and emits one deterministic projection file per work item — named by uid, and
never by slug, so a rename moves nothing (E001).

Two properties do all the work here.

**Refuse before you write (C001).** A manifest entry the tool cannot faithfully project — no uid,
a uid another entry already claimed, a phase outside the lifecycle vocabulary — aborts the *whole
run*, before the first file is written, and the report names **every** offending entry rather than
the first. A migration that half-succeeds leaves a projection tree that is neither the old truth
nor the new one, and the operator's next move (re-run? revert? hand-fix?) depends on facts the
tool destroyed on its way out. So it writes nothing, and it tells them everything.

**Mint identity separately, and record it (E001).** A uid minted *during* migration would be a
different uid on every run, and the second run would emit a second file for the same work item —
so the tool that promises byte-identical re-runs would be the tool that duplicates the corpus.
Identity is therefore backfilled by :func:`mint_uids` as its own recorded, committed step, writing
each ``uid`` back into the manifest; :func:`migrate` is strict and refuses an entry without one.
"Missing uid" is a defect precisely *because* silently inventing one is the lossy write C001 names.

Three shapes the migration deliberately does **not** carry across, each for a reason:

``issue_number`` → the store, never the projection
    The GitHub issue number is provider data. ``external_refs`` is owned by ``extension_bot``
    (``.atdd/policy/field-ownership.yaml``), so a *core* commit writing it is the wrong writer and
    the field-writer gate would refuse the migration commit — correctly. The number is preserved in
    the **store's** ``external_refs`` table, where :mod:`atdd.state.manifest_import` has always put
    it, and the mirror re-supplies it to the projection. That is the external-ref quarantine (I7)
    doing its job, not data being dropped.

``COMPLETE`` work items → archived, not projected
    ``COMPLETE`` is **derived** from merge-to-main (spec §18 decision 1) and may never be committed
    to a projection — :func:`atdd.state.projection.validate_document` refuses it. A completed work
    item therefore has no legal projection document, and inventing a phase for it ("it was probably
    SMOKE") is exactly the lossy write C001 exists to prevent. They are counted, listed, and left
    in the store; their completion lives in the merge commit that caused it. This is a **declared
    outcome, not a defect** — see :attr:`MigrationReport.archived`.

``owner_actor`` → defaulted, and said out loud
    The legacy manifest records no owner. The contract requires one. The tool defaults to
    :data:`UNATTRIBUTED_OWNER` rather than guessing a person, and ``--owner-actor`` sets it.

Dependency discipline: stdlib + ``pyyaml`` + ``atdd.state``. No provider (I7).
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import yaml

from atdd.state.identity import is_uid, mint_uid
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.projection import (
    ARCHIVED_PHASES,
    PHASES,
    PROJECTION_RELATIVE,
    STATE_ACTIVE,
    ProjectionResult,
    assert_deterministic,
    project,
    validate_document,
)
from atdd.state.store import StateStore

_log = logging.getLogger(__name__)

#: Where the legacy ledger lives, relative to the Control Root.
MANIFEST_RELATIVE = Path(".atdd") / "manifest.yaml"

#: The manifest's work-item list, and the keys that carry identity and phase.
SESSIONS_KEY = "sessions"
UID_KEY = "uid"
SLUG_KEY = "slug"
PHASE_KEY = "status"
ISSUE_KEY = "issue_number"

#: The phase a completed work item carries in the manifest — and may never carry in a projection
#: (spec §18 decision 1: COMPLETE is derived from merge-to-main). Not a defect: an outcome.
#: The projector agrees, and passes over such objects (``projection.ARCHIVED_PHASES``); the two
#: constants are bound by a test, because a migration that archived what the projector projected
#: (or vice versa) would produce a corpus that fails canonicality on its first run.
COMPLETE_PHASE = ARCHIVED_PHASES[0]

#: The owner a legacy entry has, which is none. Better a name that says so than an invented person.
UNATTRIBUTED_OWNER = "unattributed"

#: Manifest keys that become dedicated projection fields; everything else rides in the doc as-is,
#: minus the quarantined ones below.
_DIRECT_FIELDS = ("title", "body", "train")

#: Manifest keys the projection deliberately does not carry (see the module docstring).
_QUARANTINED = frozenset({ISSUE_KEY, UID_KEY, SLUG_KEY, PHASE_KEY})

#: Manifest bookkeeping the projection has no field for (``additionalProperties: false``).
_DROPPED = frozenset({"id", "file", "created", "archived", "type", "wagon", "feature",
                      "branch", "worktree", "worktree_path"})

DEFECT_MISSING_UID = "missing-uid"
DEFECT_DUPLICATE_UID = "duplicate-uid"
DEFECT_MALFORMED_UID = "malformed-uid"
DEFECT_UNKNOWN_PHASE = "unknown-phase"


class MigrationError(RuntimeError):
    """The migration could not run at all (no manifest, unreadable YAML)."""


@dataclass(frozen=True)
class MigrationDefect:
    """One manifest entry the tool cannot faithfully project, and why."""

    rule: str
    index: int
    slug: str
    field: str
    reason: str

    def render(self) -> str:
        return (
            f"sessions[{self.index}] ({self.slug or '<no slug>'}): "
            f"[{self.rule}] field {self.field!r} — {self.reason}"
        )


class LossyMigrationError(MigrationError):
    """The manifest carries entries that cannot be projected. **Nothing was written** (C001).

    Carries *every* defect, not the first: an operator fixing a manifest wants the whole list, and
    a tool that reports one defect per run turns a five-minute fix into five runs.
    """

    def __init__(self, defects: Sequence[MigrationDefect]) -> None:
        self.defects = list(defects)
        super().__init__(
            f"refusing to migrate: {len(self.defects)} manifest entr(ies) cannot be projected, "
            "so no projection file was written:\n"
            + "\n".join(f"  {defect.render()}" for defect in self.defects)
        )


@dataclass(frozen=True)
class MigrationReport:
    """What a completed :func:`migrate` run did."""

    #: uid → the projection file written for it.
    files: Dict[str, Path] = field(default_factory=dict)
    #: The digest over the whole projected set.
    digest: str = ""
    #: COMPLETE work items: hydrated into the store, deliberately not projected (see docstring).
    archived: List[str] = field(default_factory=list)
    #: GitHub issue numbers preserved in the store's external_refs (never in the projection, I7).
    quarantined_refs: int = 0
    projection_dir: Optional[Path] = None

    @property
    def migrated(self) -> int:
        return len(self.files)

    def render(self) -> str:
        lines = [
            f"migrated {self.migrated} work item(s) → {self.projection_dir}",
            f"  digest              {self.digest}",
            f"  external refs       {self.quarantined_refs} quarantined in the store (I7)",
        ]
        if self.archived:
            lines.append(
                f"  archived            {len(self.archived)} COMPLETE work item(s), not projected "
                "(COMPLETE is derived from merge-to-main — spec §18 decision 1): "
                + ", ".join(sorted(self.archived))
            )
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Reading the legacy ledger
# --------------------------------------------------------------------------- #
def manifest_path(root: Path) -> Path:
    """The legacy manifest inside ``root``."""
    return Path(root) / MANIFEST_RELATIVE


def read_manifest(path: Path) -> Dict[str, Any]:
    """Read the legacy manifest, or raise :class:`MigrationError` naming the file."""
    path = Path(path)
    if not path.is_file():
        raise MigrationError(f"no legacy manifest to migrate: {path}")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise MigrationError(f"{path} is not readable YAML: {exc}") from exc
    if not isinstance(document, dict):
        raise MigrationError(f"{path}: not a YAML mapping")
    return document


def sessions_of(document: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The manifest's work-item entries (``[]`` when it has none)."""
    sessions = document.get(SESSIONS_KEY) or []
    if not isinstance(sessions, list):
        raise MigrationError(f"manifest {SESSIONS_KEY!r} is not a list")
    return [entry for entry in sessions if isinstance(entry, dict)]


# --------------------------------------------------------------------------- #
# The refusal (C001) — every defect, before any write
# --------------------------------------------------------------------------- #
def inspect(sessions: Sequence[Mapping[str, Any]]) -> List[MigrationDefect]:
    """Every reason ``sessions`` cannot be faithfully projected. ``[]`` means: safe to migrate.

    Pure. It writes nothing, opens nothing, and returns the *whole* list — so :func:`migrate` can
    refuse the run in one piece and hand the operator every fix at once.
    """
    defects: List[MigrationDefect] = []
    claimed: Dict[str, int] = {}

    for index, entry in enumerate(sessions):
        slug = str(entry.get(SLUG_KEY) or "")
        uid = entry.get(UID_KEY)

        if uid is None or uid == "":
            defects.append(MigrationDefect(
                DEFECT_MISSING_UID, index, slug, UID_KEY,
                "no uid; identity may not be invented during a migration (run `mint-uids` first, "
                "which records one in the manifest, so re-runs stay byte-identical)",
            ))
        elif not is_uid(uid):
            defects.append(MigrationDefect(
                DEFECT_MALFORMED_UID, index, slug, UID_KEY,
                f"uid {uid!r} is not a work-item uid (expected wi_<26-char ULID>)",
            ))
        elif uid in claimed:
            defects.append(MigrationDefect(
                DEFECT_DUPLICATE_UID, index, slug, UID_KEY,
                f"uid {uid} is already claimed by sessions[{claimed[uid]}]; a uid is globally "
                "unique and never reused (spec §10 rule 1)",
            ))
        else:
            claimed[str(uid)] = index

        phase = entry.get(PHASE_KEY)
        if phase not in PHASES and phase != COMPLETE_PHASE:
            defects.append(MigrationDefect(
                DEFECT_UNKNOWN_PHASE, index, slug, PHASE_KEY,
                f"phase {phase!r} is outside the lifecycle vocabulary "
                f"{list(PHASES) + [COMPLETE_PHASE]}",
            ))

    return defects


# --------------------------------------------------------------------------- #
# Identity backfill — its own recorded step, so migration stays idempotent
# --------------------------------------------------------------------------- #
def mint_uids(path: Path, *, entropy: Optional[bytes] = None) -> Tuple[int, Path]:
    """Backfill a uid into every manifest entry that lacks one; return ``(minted, path)``.

    This is a **recorded** write: the uid lands in the manifest and is committed. That is what
    makes :func:`migrate` idempotent — the identity is decided once, by this step, and every
    subsequent projection of that work item resolves to the same file. Minting inside ``migrate``
    would instead mint afresh on each run, and the "byte-identical re-run" E001 asks for would be
    a corpus that doubles every time it is migrated.

    Idempotent itself: an entry that already carries a well-formed uid is left exactly as it is.
    """
    path = Path(path)
    document = read_manifest(path)
    sessions = document.get(SESSIONS_KEY) or []
    minted = 0
    for entry in sessions:
        if not isinstance(entry, dict):
            continue
        if is_uid(entry.get(UID_KEY)):
            continue
        entry[UID_KEY] = mint_uid(entropy=entropy)
        minted += 1

    if minted:
        path.write_text(
            yaml.safe_dump(document, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
    _log.info(
        "minted work-item uids into the legacy manifest",
        extra={"manifest": str(path), "minted": minted, "entries": len(sessions)},
    )
    return minted, path


# --------------------------------------------------------------------------- #
# Entry → projection document
# --------------------------------------------------------------------------- #
def build_document(entry: Mapping[str, Any], *, owner_actor: str = UNATTRIBUTED_OWNER) -> Dict[str, Any]:
    """The projection document for one manifest entry — pure, total, and quarantine-aware.

    Everything the contract has a field for is carried across. ``issue_number`` is **not** (it is
    the provider's, and core is not its writer); nor is the manifest's own bookkeeping, for which
    the contract has no field and ``additionalProperties: false``.
    """
    document: Dict[str, Any] = {
        "uid": str(entry[UID_KEY]),
        "phase": str(entry[PHASE_KEY]),
        "state": STATE_ACTIVE,
        "owner_actor": str(entry.get("owner_actor") or owner_actor),
        "slug": str(entry.get(SLUG_KEY) or ""),
    }
    for key in _DIRECT_FIELDS:
        value = entry.get(key)
        if value is not None:
            document[key] = value
    document.setdefault("wmbts", [])
    # Anything the manifest carried that the contract still has a field for rides along; the
    # quarantined and the unmappable do not.
    for key, value in entry.items():
        if key in _QUARANTINED or key in _DROPPED or key in document:
            continue
        document[key] = value
    return document


def build_documents(
    sessions: Sequence[Mapping[str, Any]], *, owner_actor: str = UNATTRIBUTED_OWNER,
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """``(projectable documents by uid, archived COMPLETE uids)`` — validated, nothing written.

    Refuses the whole set if any document breaks the contract or leaks nondeterministic content,
    for the same reason :func:`migrate` refuses the whole run: a half-valid corpus is worse than
    a refused one.
    """
    documents: Dict[str, Dict[str, Any]] = {}
    archived: List[str] = []
    for entry in sessions:
        uid = str(entry[UID_KEY])
        if entry.get(PHASE_KEY) == COMPLETE_PHASE:
            archived.append(uid)
            continue
        document = build_document(entry, owner_actor=owner_actor)
        assert_deterministic(document, uid=uid)
        validate_document(document)
        documents[uid] = document
    return documents, archived


# --------------------------------------------------------------------------- #
# The migration (E001)
# --------------------------------------------------------------------------- #
def hydrate_store(
    store: StateStore,
    sessions: Sequence[Mapping[str, Any]],
    *,
    owner_actor: str = UNATTRIBUTED_OWNER,
) -> int:
    """Write every work item into the store, uid-keyed; return the external refs quarantined.

    The GitHub issue number goes into the store's ``external_refs`` table and **not** into the
    projection: it is the provider's data, the bot is its declared writer, and core writing it into
    a committed document would be the wrong writer touching a field it does not own (§7.1). The
    store is where it is preserved, and the quarantine is where it stays (I7).
    """
    refs = 0
    for entry in sessions:
        uid = str(entry[UID_KEY])
        document = build_document(entry, owner_actor=owner_actor)
        data = {k: v for k, v in document.items() if k not in ("uid", "phase")}
        store.objects.upsert(  # noqa: N+1 — one upsert per work item; a bulk migration, not a query loop
            uid, WORK_ITEM_KIND, state=str(entry[PHASE_KEY]), data=data,
        )
        issue = entry.get(ISSUE_KEY)
        if issue is None:
            continue
        store.external_refs.link(  # noqa: N+1 — see above
            uid, GITHUB_PROVIDER, "issue", str(issue), data={"source": "manifest-migration"},
        )
        refs += 1
    return refs


def migrate(
    root: Path,
    *,
    store: Optional[StateStore] = None,
    out_dir: Optional[Path] = None,
    owner_actor: str = UNATTRIBUTED_OWNER,
) -> MigrationReport:
    """Migrate ``root``'s legacy manifest into the committed projection (C001 + E001).

    The order is the contract: **inspect the whole manifest, refuse the whole run, then write.**
    :class:`LossyMigrationError` is raised before a single file is created, so a manifest with one
    bad entry leaves the projection directory exactly as it found it.

    Deterministic: run it twice against the same manifest and the second run reproduces the first
    byte for byte (I1), because the uid — the only thing that names a file — was decided by
    :func:`mint_uids` and recorded, not re-rolled here.
    """
    root = Path(root)
    document = read_manifest(manifest_path(root))
    sessions = sessions_of(document)

    defects = inspect(sessions)
    if defects:
        _log.warning(
            "refusing a lossy migration; no projection file was written",
            extra={"root": str(root), "defects": [d.render() for d in defects]},
        )
        raise LossyMigrationError(defects)

    documents, archived = build_documents(sessions, owner_actor=owner_actor)
    projection_dir = Path(out_dir) if out_dir is not None else root / PROJECTION_RELATIVE

    with _store_or(store, root) as active:
        refs = hydrate_store(active, sessions, owner_actor=owner_actor)
        result: ProjectionResult = project(active, projection_dir)

    report = MigrationReport(
        files=dict(result.files), digest=result.digest, archived=sorted(archived),
        quarantined_refs=refs, projection_dir=projection_dir,
    )
    _log.info("legacy manifest migrated to the committed projection",
              extra={"root": str(root), "migrated": report.migrated,
                     "archived": len(report.archived), "refs": refs, "digest": report.digest})
    return report


class _store_or:  # noqa: N801 — a context-manager helper, used as `with _store_or(...)`
    """Use the caller's store, or open the repo's own for the duration of the run."""

    def __init__(self, store: Optional[StateStore], root: Path) -> None:
        self._given = store
        self._root = root
        self._conn: Optional[sqlite3.Connection] = None

    def __enter__(self) -> StateStore:
        if self._given is not None:
            return self._given
        from atdd.state.db import connect, init_state_store

        self._conn = connect(init_state_store(start=self._root))
        return StateStore(self._conn)

    def __exit__(self, *_exc: Any) -> None:
        if self._conn is not None:
            self._conn.close()


__all__ = [
    "COMPLETE_PHASE", "DEFECT_DUPLICATE_UID", "DEFECT_MALFORMED_UID", "DEFECT_MISSING_UID",
    "DEFECT_UNKNOWN_PHASE", "LossyMigrationError", "MANIFEST_RELATIVE", "MigrationDefect",
    "MigrationError", "MigrationReport", "PHASE_KEY", "SESSIONS_KEY", "SLUG_KEY",
    "UID_KEY", "UNATTRIBUTED_OWNER", "build_document", "build_documents", "hydrate_store",
    "inspect", "manifest_path", "migrate", "mint_uids", "read_manifest", "sessions_of",
]
