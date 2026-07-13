"""The projection merge driver — safe merges only, conflicts by design (#1400 govern-projection-fields).

Sharding the projection by uid buys the cheap half of merge safety for free: two developers
working on different objects touch different files, and git merges them without ever asking
a question (spec §7). This module is the expensive half — what to do when they touched *the
same* object.

The rule the whole wagon turns on (spec §7.2): **never blind max phase.** Taking the
further-along phase looks reasonable and is the exact mechanism by which an unevidenced
``PLANNED -> GREEN`` on a stale branch overwrites an honest ``PLANNED -> RED``, quietly,
during a merge nobody reviewed. So same-object divergence auto-merges in three cases and no
others:

1. the two sides are **identical** — there is nothing to choose between;
2. one side is a strict **no-op** — the other side's change is the only change;
3. the further phase carries **verifiable evidence for every skipped gate** — checked
   against the §6 evidence model, rung by rung, not asserted.

Everything else conflicts, and a conflict here is a *report*: the field, the writer on each
side (which is what :mod:`atdd.state.ownership`'s ``owner_actor`` and ``last_lifecycle_actor``
are on the object for), and the ownership or evidence rule that refused it. "Merge conflict
in wi_01H…yaml" tells an operator nothing they can act on.

Retirement is absorbing (K001): once an object is tombstoned in the shared truth, no merge
may bring the uid back to life, and the driver deletes no file — ever. Physical removal is
:func:`atdd.state.tombstone.compact_archive` and nothing else.

The driver is a **pure function of three documents** plus the evidence each side carries, so
it is the same code whether git invokes it as a merge driver or a test calls it directly.

Dependency discipline: stdlib + ``pyyaml`` + ``atdd.state`` only. No provider, no network.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple

import yaml

from atdd.state import evidence as evidence_model
from atdd.state import ownership
from atdd.state.ownership import (
    RULE_BOT_ONLY,
    RULE_DERIVED,
    RULE_IMMUTABLE,
    RULE_MONOTONIC_GATED,
    RULE_MUTABLE,
    RULE_POLICY_MERGE,
    RULE_SAME_DIGEST,
    RULE_SINGLE_OWNER,
    WRITER_CORE_LIFECYCLE,
    WRITER_EXTENSION_BOT,
    FieldOwnershipPolicy,
)
from atdd.state.projection import (
    STATE_ACTIVE,
    STATE_TOMBSTONED,
    canonical_bytes,
    validate_document,
)
from atdd.state.tombstone import is_tombstoned

_log = logging.getLogger(__name__)

#: The divergence cases the merge-driver matrix enumerates (C002). Three of them are the
#: §7.2 auto-merge cases; the fourth is everything the driver must refuse.
CASE_IDENTICAL = "identical"
CASE_NO_OP = "no-op"
CASE_EVIDENCE_BACKED = "evidence-backed"
CASE_UNSAFE = "unsafe"

DIVERGENCE_CASES: Tuple[str, ...] = (
    CASE_IDENTICAL, CASE_NO_OP, CASE_EVIDENCE_BACKED, CASE_UNSAFE,
)

#: The rule a resurrection is refused under — retirement is not a phase, so it is not the
#: phase ladder that refuses it (K001).
RULE_TOMBSTONE = "tombstone-absorbing"

#: The rule a file deletion is refused under (spec §10 rule 3).
RULE_NO_DELETION = "no-file-deletion"

#: Absent, as distinct from present-and-null. A field a side never set and a field a side
#: set to ``None`` are different claims, and merging them as if they were the same is how a
#: null quietly overwrites a value.
_MISSING = object()

#: Where a side's committed gate evidence lives, per object (spec §6: the evidence has to be
#: *in the commit*; CI cannot read a developer's gitignored store, and neither can a merge).
EVIDENCE_RELATIVE = Path(".atdd") / "evidence"


class MergeDriverError(RuntimeError):
    """The driver could not be run (an input fault, not a conflict)."""


# --------------------------------------------------------------------------- #
# The report — a conflict names the field, both writers, and the failing rule (R001)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Conflict:
    """One same-object divergence the driver refused, and everything needed to resolve it."""

    uid: str
    field: str
    rule: str
    ours_writer: str
    theirs_writer: str
    detail: str
    ours_value: Any = None
    theirs_value: Any = None

    def render(self) -> str:
        return (
            f"{self.uid}: {self.field} conflicts under {self.rule} — "
            f"ours written by {self.ours_writer!r}, theirs written by {self.theirs_writer!r}: "
            f"{self.detail}"
        )


@dataclass(frozen=True)
class MergeResult:
    """The outcome of merging one object: the merged document, or the reasons there is none."""

    uid: str
    merged: Optional[Dict[str, Any]] = None
    conflicts: List[Conflict] = dc_field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.conflicts

    @property
    def exit_code(self) -> int:
        """Git's merge-driver contract: ``0`` merged, non-zero conflicted."""
        return 0 if self.ok else 1

    def render(self) -> str:
        if self.ok:
            return f"{self.uid}: merged cleanly"
        lines = [f"projection merge CONFLICT ({len(self.conflicts)} field(s)) — {self.uid}:"]
        lines.extend(f"  - {conflict.render()}" for conflict in self.conflicts)
        lines.append(
            "  resolve it explicitly: the driver never picks a winner, and never resolves a "
            "phase divergence by taking the further phase (spec §7.2)."
        )
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Who wrote a field on a side (D002) — the half of a conflict report that is not the value
# --------------------------------------------------------------------------- #
def side_writer(
    document: Optional[Mapping[str, Any]], field: str, policy: FieldOwnershipPolicy
) -> str:
    """The actor that wrote ``field`` on this side of the merge.

    This is what ``owner_actor`` and ``last_lifecycle_actor`` are on the projection object
    *for* (D002). Without them a conflict report can say a body diverged but not who wrote
    either version — which leaves an operator with two anonymous strings and no way to pick
    up the phone.
    """
    if not document:
        return "<absent>"
    owner = policy.fields.get(field)
    if owner is not None and owner.writer == WRITER_EXTENSION_BOT:
        return WRITER_EXTENSION_BOT
    if owner is not None and owner.writer == WRITER_CORE_LIFECYCLE:
        actor = document.get("last_lifecycle_actor") or document.get("owner_actor")
        return str(actor) if actor else "<unknown>"
    actor = document.get("owner_actor")
    return str(actor) if actor else "<unknown>"


# --------------------------------------------------------------------------- #
# Field-level merge rules (spec §7.1) — each one reads its declaration, not its field name
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Cell:
    """One field's three values, plus everything a rule needs to judge them."""

    uid: str
    field: str
    rule: str
    base: Any
    ours: Any
    theirs: Any
    base_doc: Mapping[str, Any]
    ours_doc: Mapping[str, Any]
    theirs_doc: Mapping[str, Any]
    ours_evidence: FrozenSet[str]
    theirs_evidence: FrozenSet[str]
    policy: FieldOwnershipPolicy

    @property
    def ours_changed(self) -> bool:
        return self.ours != self.base

    @property
    def theirs_changed(self) -> bool:
        return self.theirs != self.base

    def conflict(self, detail: str) -> Conflict:
        return Conflict(
            uid=self.uid,
            field=self.field,
            rule=self.rule,
            ours_writer=side_writer(self.ours_doc, self.field, self.policy),
            theirs_writer=side_writer(self.theirs_doc, self.field, self.policy),
            detail=detail,
            ours_value=None if self.ours is _MISSING else self.ours,
            theirs_value=None if self.theirs is _MISSING else self.theirs,
        )


_Outcome = Tuple[Any, Optional[Conflict]]


def _trivial(cell: _Cell) -> Optional[_Outcome]:
    """The two cases every rule shares: the sides agree, or one of them did nothing."""
    if cell.ours == cell.theirs:
        return cell.ours, None
    if not cell.ours_changed:
        return cell.theirs, None
    if not cell.theirs_changed:
        return cell.ours, None
    return None


def _immutable(cell: _Cell) -> _Outcome:
    """``uid``: minted once, never rewritten — not by a merge either."""
    if not cell.ours_changed and not cell.theirs_changed:
        return cell.base, None
    return None, cell.conflict(
        f"{cell.field} is immutable: it is minted once and names the projection file; a merge "
        "cannot rewrite identity"
    )


def _mutable(cell: _Cell) -> _Outcome:
    """Display metadata: merge when only one side moved, conflict when both did."""
    trivial = _trivial(cell)
    if trivial is not None:
        return trivial
    return None, cell.conflict(
        f"both sides set {cell.field} to different values; display metadata has one writer per "
        "object and no rule for choosing between two"
    )


def _monotonic_gated(cell: _Cell) -> _Outcome:
    """``phase``/``state``: forward only, and a skip must carry the evidence it skipped past.

    The three §7.2 safe cases, in order — and nothing else. When both sides advanced, the
    further one is admitted **only** if it carries evidence for every gate the jump from the
    *base* phase passes through. That is what makes this a gate rather than a comparison.
    """
    if cell.field == "state":
        return _merge_state(cell)

    trivial = _trivial(cell)
    if trivial is not None:
        value = trivial[0]
        backward = _behind(value, cell.base)
        if backward:
            return None, cell.conflict(
                f"phase is monotonic: {value!r} is behind {cell.base!r} on the ladder "
                f"{list(evidence_model.PHASE_LADDER)}"
            )
        return trivial

    further, nearer, further_evidence, side = _further(cell)
    violations = evidence_model.check_transition(
        cell.uid, _phase_or_none(cell.base), further, further_evidence,
    )
    if violations:
        return None, cell.conflict(
            f"both sides advanced the phase and they disagree (ours {cell.ours!r}, theirs "
            f"{cell.theirs!r}); the further phase {further!r} on {side} carries no evidence for "
            f"every gate it skipped: {violations[0].detail}. The driver does not resolve a phase "
            "divergence by taking the further phase (spec §7.2)"
        )
    _log.info(
        "phase divergence auto-merged on evidence",
        extra={"uid": cell.uid, "further": further, "nearer": nearer},
    )
    return further, None


def _merge_state(cell: _Cell) -> _Outcome:
    """``state``: ``TOMBSTONED`` absorbs. Resurrection is refused before we ever get here."""
    if STATE_TOMBSTONED in (cell.ours, cell.theirs, cell.base):
        return STATE_TOMBSTONED, None
    trivial = _trivial(cell)
    if trivial is not None:
        return trivial
    return None, cell.conflict("the two sides claim different object states")


def _single_owner(cell: _Cell) -> _Outcome:
    """``body``: one side may move it, and only if the object has a single owner (D002).

    Two writers editing one body is not a merge problem, it is a coordination problem: there
    is no rule that combines two prose rewrites, and picking one silently discards the other.
    """
    if cell.ours == cell.theirs:
        return cell.ours, None
    owner = _single_owner_actor(cell)
    trivial = _trivial(cell)
    if trivial is not None and owner is not None:
        return trivial
    if trivial is not None:
        return None, cell.conflict(
            f"{cell.field} moved while the object changed hands (owners "
            f"{sorted(_owners(cell))}); the single-owner rule cannot prove the writer owned it"
        )
    return None, cell.conflict(
        f"both sides rewrote {cell.field} and the single-owner rule cannot prove either safe; "
        "two writers edited one body and no merge can combine them"
    )


def _same_digest(cell: _Cell) -> _Outcome:
    """``train``/``tombstone``: identical is safe, divergent is a decision, not a merge."""
    trivial = _trivial(cell)
    if trivial is not None:
        return trivial
    return None, cell.conflict(
        f"the two sides carry different {cell.field} values, so they do not share a digest; "
        "which one is correct is an operator decision"
    )


def _policy_merge(cell: _Cell) -> _Outcome:
    """``wmbts``: test-owned. Disjoint additions union; a contradicted entry conflicts."""
    trivial = _trivial(cell)
    if trivial is not None:
        return trivial
    base = _by_key(_as_list(cell.base))
    ours = _by_key(_as_list(cell.ours))
    theirs = _by_key(_as_list(cell.theirs))
    merged: Dict[str, Any] = {}
    contradicted: List[str] = []
    for key in sorted(set(base) | set(ours) | set(theirs)):
        old = base.get(key, _MISSING)
        left = ours.get(key, _MISSING)
        right = theirs.get(key, _MISSING)
        if left == right:
            value = left
        elif left == old:
            value = right
        elif right == old:
            value = left
        else:
            contradicted.append(key)
            continue
        if value is not _MISSING:
            merged[key] = value
    if contradicted:
        return None, cell.conflict(
            f"both sides changed the same {cell.field} entr(y/ies) {contradicted} to different "
            "content; the policy merges disjoint additions, never contradictory ones"
        )
    return canonical_list(merged.values()), None


def _derived(cell: _Cell) -> _Outcome:
    """Derived values: disjoint keys union; the same key with two values is a fault."""
    if isinstance(cell.ours, Mapping) or isinstance(cell.theirs, Mapping):
        return _merge_mapping(cell)
    trivial = _trivial(cell)
    if trivial is not None:
        return trivial
    return None, cell.conflict(
        f"{cell.field} is derived and the two sides derived different values; one of the two "
        "inputs is stale"
    )


def _bot_only(cell: _Cell) -> _Outcome:
    """``external_refs``: the bot's subtree. Disjoint providers union; a clash conflicts.

    Non-authoritative (spec §8.2 rule 5) — but "non-authoritative" is not "arbitrary": a
    merge that silently picked one provider's ref over another would still be a merge that
    lost data nobody agreed to lose.
    """
    return _merge_mapping(cell)


def _merge_mapping(cell: _Cell) -> _Outcome:
    """Per-key three-way merge of a mapping field, conflicting only on contradicted keys."""
    trivial = _trivial(cell)
    if trivial is not None:
        return trivial
    base = dict(cell.base) if isinstance(cell.base, Mapping) else {}
    ours = dict(cell.ours) if isinstance(cell.ours, Mapping) else {}
    theirs = dict(cell.theirs) if isinstance(cell.theirs, Mapping) else {}
    merged: Dict[str, Any] = {}
    contradicted: List[str] = []
    for key in sorted(set(base) | set(ours) | set(theirs)):
        old = base.get(key, _MISSING)
        left = ours.get(key, _MISSING)
        right = theirs.get(key, _MISSING)
        if left == right:
            value = left
        elif left == old:
            value = right
        elif right == old:
            value = left
        else:
            contradicted.append(key)
            continue
        if value is not _MISSING:
            merged[key] = value
    if contradicted:
        return None, cell.conflict(
            f"both sides set {cell.field}.{contradicted[0]} to different values"
            + (f" (and {len(contradicted) - 1} more)" if len(contradicted) > 1 else "")
        )
    return merged, None


#: Rule → the function that merges a field governed by it. The driver dispatches on the
#: *declared* rule, never on the field's name: a field whose ownership changes changes how it
#: merges by editing the policy, not by editing this module.
RULE_MERGERS = {
    RULE_IMMUTABLE: _immutable,
    RULE_MUTABLE: _mutable,
    RULE_MONOTONIC_GATED: _monotonic_gated,
    RULE_SINGLE_OWNER: _single_owner,
    RULE_SAME_DIGEST: _same_digest,
    RULE_POLICY_MERGE: _policy_merge,
    RULE_DERIVED: _derived,
    RULE_BOT_ONLY: _bot_only,
}


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _phase_or_none(value: Any) -> Optional[str]:
    return None if value is _MISSING or value is None else str(value)


def _rank(phase: Any) -> int:
    return evidence_model.PHASE_RANK.get(_phase_or_none(phase) or "", -1)


def _behind(value: Any, base: Any) -> bool:
    return _rank(value) >= 0 and _rank(base) >= 0 and _rank(value) < _rank(base)


def _further(cell: _Cell) -> Tuple[str, str, FrozenSet[str], str]:
    """``(further, nearer, the further side's evidence, which side that was)``."""
    if _rank(cell.ours) >= _rank(cell.theirs):
        return str(cell.ours), str(cell.theirs), cell.ours_evidence, "ours"
    return str(cell.theirs), str(cell.ours), cell.theirs_evidence, "theirs"


def _owners(cell: _Cell) -> set:
    return {
        str(doc.get("owner_actor"))
        for doc in (cell.base_doc, cell.ours_doc, cell.theirs_doc)
        if doc and doc.get("owner_actor")
    }


def _single_owner_actor(cell: _Cell) -> Optional[str]:
    owners = _owners(cell)
    return next(iter(owners)) if len(owners) == 1 else None


def _as_list(value: Any) -> List[Any]:
    if value is _MISSING or value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _by_key(items: Iterable[Any]) -> Dict[str, Any]:
    """Index a sequence by its entries' identity — a urn/id when they have one, else content."""
    keyed: Dict[str, Any] = {}
    for item in items:
        if isinstance(item, Mapping):
            key = str(item.get("urn") or item.get("id") or sorted(item.items()))
        else:
            key = str(item)
        keyed[key] = item
    return keyed


def canonical_list(values: Iterable[Any]) -> List[Any]:
    """A content-ordered list — the projector's canonical order, so the merge stays canonical.

    The same key :func:`atdd.state.projection.canonicalize` sorts by, and for the same reason:
    the merged object must be byte-identical to the projection of the merged state, and an
    insertion-ordered list would not be (I1).
    """
    import json

    return sorted(values, key=lambda v: json.dumps(v, sort_keys=True, default=str))


# --------------------------------------------------------------------------- #
# The object merge (E002, R001, K001)
# --------------------------------------------------------------------------- #
def _resurrection(
    uid: str,
    base: Optional[Mapping[str, Any]],
    ours: Optional[Mapping[str, Any]],
    theirs: Optional[Mapping[str, Any]],
    policy: FieldOwnershipPolicy,
) -> Optional[Conflict]:
    """Refuse any merge that brings a tombstoned uid back to life (K001).

    A side that did not change the object cannot resurrect it — that is the ordinary case of
    one developer retiring an object while the other left it alone, and it merges. A side
    that *did* change it, while the object is tombstoned anywhere in the merge, is claiming a
    live object over a retirement, and there is no reading of that which is safe.
    """
    if not any(is_tombstoned(doc) for doc in (base, ours, theirs)):
        return None
    for label, side in (("ours", ours), ("theirs", theirs)):
        if side is None or is_tombstoned(side):
            continue
        if base is not None and dict(side) == dict(base):
            continue  # untouched by this side; it is not reviving anything
        return Conflict(
            uid=uid,
            field="state",
            rule=RULE_TOMBSTONE,
            ours_writer=side_writer(ours, "state", policy),
            theirs_writer=side_writer(theirs, "state", policy),
            detail=(
                f"{uid} is TOMBSTONED, and the {label} side sets a live phase "
                f"{side.get('phase')!r} (state {side.get('state', STATE_ACTIVE)!r}) on it; a "
                "tombstone is a record and no merge may revive the uid (spec §10 rule 3)"
            ),
            ours_value=None if ours is None else ours.get("state"),
            theirs_value=None if theirs is None else theirs.get("state"),
        )
    return None


def merge_object(
    uid: str,
    base: Optional[Mapping[str, Any]],
    ours: Optional[Mapping[str, Any]],
    theirs: Optional[Mapping[str, Any]],
    *,
    policy: Optional[FieldOwnershipPolicy] = None,
    ours_evidence: Iterable[str] = (),
    theirs_evidence: Iterable[str] = (),
) -> MergeResult:
    """Three-way merge one projection object under the field-ownership policy (E002, R001).

    Every field is merged by its *declared* rule. A conflict on any field means the whole
    object conflicts and **no merged document is produced** — a half-merged object written to
    disk would be a state neither developer authored.
    """
    policy = policy or ownership.default_policy()
    ours_ev, theirs_ev = frozenset(ours_evidence), frozenset(theirs_evidence)

    deletion = _deletion_conflict(uid, base, ours, theirs, policy)
    if deletion is not None:
        return MergeResult(uid=uid, merged=None, conflicts=[deletion])

    resurrection = _resurrection(uid, base, ours, theirs, policy)
    if resurrection is not None:
        _log.warning("projection merge refused a resurrection", extra={"uid": uid})
        return MergeResult(uid=uid, merged=None, conflicts=[resurrection])

    base_doc = dict(base or {})
    ours_doc = dict(ours or {})
    theirs_doc = dict(theirs or {})

    merged: Dict[str, Any] = {}
    conflicts: List[Conflict] = []
    for name in sorted(set(base_doc) | set(ours_doc) | set(theirs_doc)):
        if name not in policy:
            conflicts.append(Conflict(
                uid=uid, field=name, rule="unowned",
                ours_writer=side_writer(ours_doc, name, policy),
                theirs_writer=side_writer(theirs_doc, name, policy),
                detail="the field-ownership policy declares no writer and no merge rule for "
                       "this field, so the driver has nothing to merge it by (C001)",
            ))
            continue
        rule = policy.rule_of(name)
        merger = RULE_MERGERS.get(rule)
        if merger is None:
            conflicts.append(Conflict(
                uid=uid, field=name, rule=rule,
                ours_writer=side_writer(ours_doc, name, policy),
                theirs_writer=side_writer(theirs_doc, name, policy),
                detail=f"the policy declares merge rule {rule!r}, which the driver implements no "
                       f"merger for (the implemented set is {sorted(RULE_MERGERS)})",
            ))
            continue
        cell = _Cell(
            uid=uid, field=name, rule=rule,
            base=base_doc.get(name, _MISSING),
            ours=ours_doc.get(name, _MISSING),
            theirs=theirs_doc.get(name, _MISSING),
            base_doc=base_doc, ours_doc=ours_doc, theirs_doc=theirs_doc,
            ours_evidence=ours_ev, theirs_evidence=theirs_ev,
            policy=policy,
        )
        value, conflict = merger(cell)
        if conflict is not None:
            conflicts.append(conflict)
            continue
        if value is not _MISSING:
            merged[name] = value

    if conflicts:
        _log.warning(
            "projection merge conflicted",
            extra={"uid": uid, "fields": [c.field for c in conflicts]},
        )
        return MergeResult(uid=uid, merged=None, conflicts=conflicts)

    validate_document(merged)
    return MergeResult(uid=uid, merged=merged, conflicts=[])


def _deletion_conflict(
    uid: str,
    base: Optional[Mapping[str, Any]],
    ours: Optional[Mapping[str, Any]],
    theirs: Optional[Mapping[str, Any]],
    policy: FieldOwnershipPolicy,
) -> Optional[Conflict]:
    """A side that deleted the projection file has expressed retirement the one illegal way."""
    if base is None:
        return None
    for label, side in (("ours", ours), ("theirs", theirs)):
        if side is None:
            return Conflict(
                uid=uid, field="<file>", rule=RULE_NO_DELETION,
                ours_writer=side_writer(ours, "state", policy),
                theirs_writer=side_writer(theirs, "state", policy),
                detail=f"the {label} side deleted the projection file; retirement is a tombstone "
                       "record, never a file deletion (spec §10 rule 3) — use "
                       "`atdd state author tombstone`",
            )
    return None


# --------------------------------------------------------------------------- #
# The git merge driver (E002) — `merge.atdd-projection.driver` over %O %A %B
# --------------------------------------------------------------------------- #
def _load(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None:
        return None
    path = Path(path)
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return None
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        raise MergeDriverError(f"{path}: a projection object is a YAML mapping")
    return document


def merge_files(
    base_path: Optional[Path],
    ours_path: Path,
    theirs_path: Path,
    *,
    output: Optional[Path] = None,
    policy: Optional[FieldOwnershipPolicy] = None,
    ours_evidence: Iterable[str] = (),
    theirs_evidence: Iterable[str] = (),
) -> MergeResult:
    """Git's merge-driver entry point: merge ``%O %A %B``, writing the result over ``%A``.

    On conflict **nothing is written** (R001): git keeps ours in the worktree and reports the
    conflict, and the operator resolves it with the report in hand. A driver that wrote a
    "best effort" merged file on conflict would be back to picking a winner.
    """
    base = _load(base_path)
    ours = _load(ours_path)
    theirs = _load(theirs_path)
    if ours is None and theirs is None:
        raise MergeDriverError("neither side of the merge carries a projection object")

    uid = str((ours or theirs or base or {}).get("uid") or Path(ours_path).stem)
    result = merge_object(
        uid, base, ours, theirs,
        policy=policy, ours_evidence=ours_evidence, theirs_evidence=theirs_evidence,
    )
    if result.ok and result.merged is not None:
        target = Path(output or ours_path)
        target.write_bytes(canonical_bytes(result.merged))
    return result
