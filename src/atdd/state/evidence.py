"""The lifecycle evidence model and the legal-transition validator (#1400 enforce-merge-authority).

The load-bearing gate (spec §4): *canonical YAML alone is only well-formatted text; it
is not correctness.* A projection that is byte-perfect, schema-valid, and jumps
``PLANNED -> GREEN`` with no failing-test evidence and no operator token is exactly as
canonical as one that walked the lifecycle honestly. This module is what tells them
apart, by diffing the committed projection against the merge-base and checking each
phase change against the §6 evidence table (I4).

The policy is data, not code: :data:`EVIDENCE_POLICY` is a ``commons:projection-evidence``
document (``contracts/commons/projection-evidence.schema.json``). Three properties fall
out of it and are the whole of the validator's contract:

- **Monotonic.** ``GREEN -> RED`` is rejected as non-monotonic. Retirement is the one
  exception: ``* -> TOMBSTONED`` leaves the ladder, and is admitted only with a reason
  digest and tombstone metadata (spec §10 rule 3 — a tombstone, never a file deletion).
- **No unevidenced skip.** ``PLANNED -> GREEN`` is not forbidden *because* it skips RED;
  it is forbidden unless it carries the evidence every skipped gate would have demanded.
  So the validator walks the ladder rung by rung and accumulates each rung's ``requires``.
- **COMPLETE is derived, never stored** (spec §18 decision 1). A committed projection
  asserting ``phase: COMPLETE`` is invalid, not merely stale: storing it reintroduces
  the post-merge mutation the whole model exists to remove.

Every rejection carries the uid, the attempted transition, and the failed clause — a
report that names only "illegal" gives an operator nothing to act on.

The second half of this module (below the divider) is the **smoke-execution
attestation** (#1602): the record that a live-smoke test actually RAN. It is a
different kind of evidence from the projection-diff tokens above — those are
*derived from a commit* at merge-authority time, this one is *captured by the
test run itself* — so the two are kept apart deliberately and share nothing but
this file. In particular ``evidence_for``'s ``smoke_evidence_artifact``
derivation is NOT extended to read it: the merge authority may only read what is
in the commit, and a run artifact is not.

Dependency discipline: stdlib + ``atdd.state`` only. No provider, and in particular no
``external_refs`` is ever consulted for a lifecycle decision (I7, spec §8.2 rule 5) —
which is why every attestation function below is keyed by **work-item uid** and never
by a provider-side issue number. Resolving an issue number to a uid is the caller's
job, one layer up.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import (
    Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Set, Tuple,
)

from atdd.state.projection import STATE_TOMBSTONED

_log = logging.getLogger(__name__)

#: Retirement is a *state*, not a rung on the phase ladder — but a transition into it is
#: still a transition, and the evidence model gates it like any other.
TOMBSTONED = "TOMBSTONED"

#: The phase ladder, in order. Position is what makes "backward" and "skipping"
#: meaningful; a phase outside it has no rung, so no transition can be derived for it.
#:
#: It is the linear spine of the phase machine
#: (``src/atdd/coach/conventions/phase_machine.convention.yaml``), and it must stay that
#: way: ``REFACTOR`` was missing here while :data:`atdd.state.projection.PHASES` carried
#: it, so every ``SMOKE -> REFACTOR`` advance — the only legal way out of SMOKE — read as
#: ``unknown_transition`` and hard-failed the merge (#1602). ``BLOCKED`` and ``OBSOLETE``
#: are deliberately absent: they are escapes off the spine, not rungs on it, and they have
#: no ordering relative to the rungs. ``test_phase_ladder_matches_projection_phases.py``
#: is the tie that keeps the three in step.
PHASE_LADDER: Tuple[str, ...] = (
    "INIT", "PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE",
)

#: Rung index by phase.
PHASE_RANK: Dict[str, int] = {phase: index for index, phase in enumerate(PHASE_LADDER)}

#: The §6 lifecycle evidence table, as a ``commons:projection-evidence`` document.
#: An entry with **no** ``from`` key is a wildcard source (``* -> TOMBSTONED``); an entry
#: with ``from: null`` is the mint (``∅ -> INIT``).
EVIDENCE_POLICY: Dict[str, Any] = {
    "complete_is_derived": True,
    "transitions": [
        {
            "from": None,
            "to": "INIT",
            "requires": ["uid_generated", "body_initialized", "projection_digest"],
        },
        {
            "from": "INIT",
            "to": "PLANNED",
            "requires": ["plan_complete", "acceptance_or_wmbt_refs"],
        },
        {
            "from": "PLANNED",
            "to": "RED",
            "requires": ["operator_token_digest", "gate_id", "failing_test_evidence"],
        },
        {
            "from": "RED",
            "to": "GREEN",
            "requires": ["passing_test_evidence", "implementation_diff"],
        },
        {
            "from": "GREEN",
            "to": "SMOKE",
            "requires": ["smoke_evidence_artifact"],
        },
        {
            # The only legal way out of SMOKE (phase_machine.convention.yaml). It demands
            # the same artifact GREEN->SMOKE did, which is the point rather than an
            # oversight: it is the gate COACH-RATCHET-PRES-001 already enforces locally
            # (`.atdd/smoke-evidence/<N>.yaml`), restated where the merge authority can
            # see it. A rung that demanded nothing could not exist — `requires` is
            # `minItems: 1` in commons:projection-evidence.
            "from": "SMOKE",
            "to": "REFACTOR",
            "requires": ["smoke_evidence_artifact"],
        },
        {
            "from": "REFACTOR",
            "to": "COMPLETE",
            "requires": ["derived_from_merge_to_main"],
            "derived": True,
        },
        {
            # No `from`: retirement may leave any phase (spec §6, `* -> TOMBSTONED`).
            "to": TOMBSTONED,
            "requires": ["reason_digest", "tombstone_metadata"],
        },
    ],
}

#: Clause names a rejection can carry. They are the vocabulary an operator greps for.
CLAUSE_NON_MONOTONIC = "non_monotonic"
CLAUSE_SKIPPED_GATE = "skipped_gate"
CLAUSE_MISSING_EVIDENCE = "missing_evidence"
CLAUSE_UNKNOWN_TRANSITION = "unknown_transition"
CLAUSE_COMPLETE_IS_DERIVED = "complete_is_derived"
CLAUSE_TOMBSTONE_EVIDENCE = "tombstone_evidence"


def _entry(from_phase: Optional[str], to_phase: str) -> Optional[Mapping[str, Any]]:
    """The policy entry for ``from_phase -> to_phase``, or ``None`` when none exists."""
    for candidate in EVIDENCE_POLICY["transitions"]:
        if candidate["to"] != to_phase:
            continue
        if "from" not in candidate:  # the `* -> TOMBSTONED` wildcard
            return candidate
        if candidate["from"] == from_phase:
            return candidate
    return None


def requires_for(from_phase: Optional[str], to_phase: str) -> Optional[Tuple[str, ...]]:
    """The evidence ``from_phase -> to_phase`` demands, or ``None`` when it has no entry."""
    entry = _entry(from_phase, to_phase)
    return tuple(entry["requires"]) if entry is not None else None


def gate_path(from_phase: Optional[str], to_phase: str) -> Optional[List[Tuple[str, str]]]:
    """The gates a jump from ``from_phase`` to ``to_phase`` passes through, in order.

    ``PLANNED -> GREEN`` is not one gate; it is two — ``PLANNED->RED`` and ``RED->GREEN``
    — and the jump is admissible only if it carries the evidence *both* would have
    demanded (spec §7.2 clause 3). Returns ``None`` when the pair is not a forward walk
    of the ladder, which is the caller's cue that a different clause applies.
    """
    if from_phase is None or from_phase not in PHASE_RANK or to_phase not in PHASE_RANK:
        return None
    start, stop = PHASE_RANK[from_phase], PHASE_RANK[to_phase]
    if stop <= start:
        return None
    return [(PHASE_LADDER[i], PHASE_LADDER[i + 1]) for i in range(start, stop)]


@dataclass(frozen=True)
class Violation:
    """One rejected transition, named well enough to act on."""

    uid: str
    transition: str
    clause: str
    detail: str

    def render(self) -> str:
        return f"{self.uid}: {self.transition} rejected [{self.clause}] — {self.detail}"


@dataclass(frozen=True)
class TransitionReport:
    """The outcome of the legal-transition validator over a projection diff."""

    checked: int
    violations: List[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def render(self) -> str:
        if self.ok:
            return f"every transition is lifecycle-legal ({self.checked} change(s))"
        lines = [
            f"illegal transition(s) rejected ({len(self.violations)}/{self.checked} change(s)):"
        ]
        lines.extend(f"  - {violation.render()}" for violation in self.violations)
        return "\n".join(lines)


@dataclass(frozen=True)
class PhaseChange:
    """One object's phase movement between the merge-base and the head projection."""

    uid: str
    before: Optional[str]
    after: str

    @property
    def transition(self) -> str:
        return f"{self.before or '∅'}->{self.after}"


def check_transition(
    uid: str,
    before: Optional[str],
    after: str,
    evidence: Iterable[str],
) -> List[Violation]:
    """Every clause ``before -> after`` fails, given the ``evidence`` it carries (C001).

    Returns an empty list when the transition is admissible. A transition is checked in
    one order and one order only, because the clauses are not independent: a backward
    move is rejected as non-monotonic *before* its evidence is weighed, since no amount
    of evidence makes ``GREEN -> RED`` a legal shared claim.
    """
    have: Set[str] = set(evidence)
    transition = f"{before or '∅'}->{after}"
    violations: List[Violation] = []

    if after == TOMBSTONED:
        missing = [token for token in requires_for(before, TOMBSTONED) or () if token not in have]
        if missing:
            violations.append(Violation(
                uid, transition, CLAUSE_TOMBSTONE_EVIDENCE,
                f"retirement requires {sorted(missing)}; a tombstone is a record, not a deletion",
            ))
        return violations

    if after == "COMPLETE":
        # Not "not yet supported" — *invalid*. COMPLETE is derived from merge-to-main
        # (spec §18 decision 1); a stored COMPLETE reintroduces post-merge mutation.
        return [Violation(
            uid, transition, CLAUSE_COMPLETE_IS_DERIVED,
            "COMPLETE is derived from merge-to-main and may never be stored in the projection",
        )]

    if before is not None and (before not in PHASE_RANK or after not in PHASE_RANK):
        return [Violation(
            uid, transition, CLAUSE_UNKNOWN_TRANSITION,
            f"no evidence-policy entry: one of {before!r}/{after!r} is off the phase ladder "
            f"{list(PHASE_LADDER)}",
        )]

    if before is not None and PHASE_RANK[after] < PHASE_RANK[before]:
        return [Violation(
            uid, transition, CLAUSE_NON_MONOTONIC,
            f"phase is monotonic: {after} is behind {before} on the ladder",
        )]

    if before is not None and PHASE_RANK[after] == PHASE_RANK[before]:
        return []  # a no-op phase-wise; other validators cover the rest of the diff

    if before is None:
        # A newly-committed object is born at INIT and walks up from there. Introducing it
        # straight into PLANNED does not skip the mint — it just leaves it unevidenced.
        gates: Optional[List[Tuple[Optional[str], str]]] = [(None, "INIT")]
        if after != "INIT":
            walk = gate_path("INIT", after)
            gates = None if walk is None else gates + list(walk)
    else:
        gates = gate_path(before, after)
    if gates is None:
        return [Violation(
            uid, transition, CLAUSE_UNKNOWN_TRANSITION,
            f"no evidence-policy entry for {transition}",
        )]

    for gate_from, gate_to in gates:
        needed = requires_for(gate_from, gate_to)
        gate_name = f"{gate_from or '∅'}->{gate_to}"
        if needed is None:
            violations.append(Violation(
                uid, transition, CLAUSE_UNKNOWN_TRANSITION,
                f"no evidence-policy entry for the gate {gate_name}",
            ))
            continue
        missing = [token for token in needed if token not in have]
        if not missing:
            continue
        clause = CLAUSE_SKIPPED_GATE if gate_name != transition else CLAUSE_MISSING_EVIDENCE
        skipped = " (skipped)" if gate_name != transition else ""
        violations.append(Violation(
            uid, transition, clause,
            f"the gate {gate_name}{skipped} requires {sorted(missing)}, and the commit "
            "carries no such evidence",
        ))
    return violations


def diff_phases(
    base: Mapping[str, Mapping[str, Any]],
    head: Mapping[str, Mapping[str, Any]],
) -> List[PhaseChange]:
    """Every object whose phase or state moved between two projections.

    A tombstoned head document reads as a transition to ``TOMBSTONED`` whatever its
    phase field says: the tombstone is the claim being made, and the phase it retired
    from is not it.
    """
    changes: List[PhaseChange] = []
    for uid in sorted(set(base) | set(head)):
        if uid not in head:
            continue  # a removed file is a field/ownership fault, not a transition
        after_doc = head[uid]
        before_doc = base.get(uid)
        before = None if before_doc is None else str(before_doc.get("phase"))
        after = (
            TOMBSTONED if after_doc.get("state") == STATE_TOMBSTONED
            else str(after_doc.get("phase"))
        )
        if before_doc is not None:
            was_tombstoned = before_doc.get("state") == STATE_TOMBSTONED
            if was_tombstoned:
                before = TOMBSTONED
            if before == after:
                continue
        changes.append(PhaseChange(uid=uid, before=before, after=after))
    return changes


#: Prefix of the committed merge-authority evidence artifact. It must stay equal to
#: ``merge_driver.EVIDENCE_RELATIVE``, which is the module that OWNS the path; it is
#: restated rather than imported to keep this module's hot path free of the driver,
#: and ``test_evidence_token_derivation_paths.py`` is the tie that stops the two
#: literals from drifting apart.
_MERGE_EVIDENCE_PREFIX = ".atdd/evidence/"

#: The evidence tokens a *document* can attest to on its own.
_DOCUMENT_TOKENS: FrozenSet[str] = frozenset({
    "uid_generated", "body_initialized", "plan_complete", "acceptance_or_wmbt_refs",
    "reason_digest", "tombstone_metadata",
})


def evidence_for(
    document: Mapping[str, Any],
    changed_paths: Sequence[str],
    group: Optional[Any] = None,
) -> Set[str]:
    """The evidence tokens a committed change actually carries (the v1 derivation).

    Three sources, and only three — every one of them is *in the commit*, which is the
    point: CI cannot read a developer's gitignored store, so evidence that is not
    committed does not exist as far as the merge authority is concerned.

    1. the head projection document (identity, body, plan refs, tombstone metadata);
    2. the commit's ATDD trailer ``group`` (operator token digest, gate id, projection
       digest) — the operator's approval reaches CI as a digest, never as a token (I8);
    3. the commit's changed paths (test evidence, implementation diff, smoke artifact).

    ⚠️ v1 derivation, deliberately mechanical: a changed test file under the acceptance
    tree attests to *test evidence*, and the merge-authority run's own test job is what
    makes it *passing* test evidence. Distinguishing failing from passing from paths
    alone is not possible, and pretending otherwise would be worse than saying so.
    """
    tokens: Set[str] = set()
    if document.get("uid"):
        tokens.add("uid_generated")
    if str(document.get("body") or "").strip():
        tokens.add("body_initialized")
        tokens.add("plan_complete")
    if document.get("wmbts"):
        tokens.add("acceptance_or_wmbt_refs")
    tombstone = document.get("tombstone")
    if isinstance(tombstone, Mapping) and tombstone:
        tokens.add("tombstone_metadata")
        if tombstone.get("reason_digest"):
            tokens.add("reason_digest")

    if group is not None:
        if getattr(group, "token_digest", None):
            tokens.add("operator_token_digest")
        if getattr(group, "gate", None):
            tokens.add("gate_id")
        if getattr(group, "projection_digest", None):
            tokens.add("projection_digest")

    for path in changed_paths:
        name = path.rsplit("/", 1)[-1]
        if name.startswith("test_") and name.endswith(".py"):
            tokens.add("failing_test_evidence")
            tokens.add("passing_test_evidence")
            if "smoke" in name or "/smoke" in path:
                tokens.add("smoke_evidence_artifact")
        elif path.startswith(_MERGE_EVIDENCE_PREFIX):
            # ``.atdd/evidence/<uid>/<gate>.yaml`` — the COMMITTED, per-gate merge
            # authority artifact (``merge_driver.EVIDENCE_RELATIVE``), read back out
            # of the object database by ``govern_cli._evidence_at``. Committed is the
            # requirement, not an accident: evidence a merge cannot see is evidence
            # the merge does not have (spec §6).
            #
            # NOT to be "aligned" with ``.atdd/smoke-evidence/<N>.yaml``, which looks
            # like a near-miss of this name and is a different artifact entirely: the
            # #358 presentation ratchet's local, .gitignore'd, operator-TYPED stamp,
            # writable by `atdd validate coder --smoke-required` without running a
            # test. Pointing this branch at it would either never fire (a gitignored
            # path never appears in a commit's changed paths) or, if that ignore were
            # lifted, mint smoke_evidence_artifact from a typed stamp — inventing a
            # brand-new false green in the merge authority. #1602 closed that bug
            # class; ``test_evidence_token_derivation_paths.py`` keeps it closed.
            tokens.add("smoke_evidence_artifact")
        elif path.startswith("src/") and path.endswith(".py"):
            tokens.add("implementation_diff")
    return tokens


def validate_projection_diff(
    base: Mapping[str, Mapping[str, Any]],
    head: Mapping[str, Mapping[str, Any]],
    evidence_by_uid: Mapping[str, Iterable[str]],
) -> TransitionReport:
    """Check every phase change between two projections against the §6 model (C001).

    This is the gate the whole wagon exists for: it is what makes a *canonical* diff
    that is nonetheless a lie fail to merge.
    """
    changes = diff_phases(base, head)
    violations: List[Violation] = []
    for change in changes:
        violations.extend(check_transition(
            change.uid, change.before, change.after, evidence_by_uid.get(change.uid, ()),
        ))
    if violations:
        _log.warning(
            "illegal transition(s) in the projection diff",
            extra={"changes": len(changes), "violations": len(violations)},
        )
    return TransitionReport(checked=len(changes), violations=violations)
