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

- **Monotonic.** ``GREEN -> RED`` is rejected as non-monotonic. The edges that leave the
  ladder rather than climb it are gated on their own terms: ``* -> TOMBSTONED`` on a
  reason digest and tombstone metadata (spec §10 rule 3 — a tombstone, never a file
  deletion), the escapes on an operator sign-off (:data:`ESCAPES`).
- **No unevidenced skip.** ``PLANNED -> GREEN`` is not forbidden *because* it skips RED;
  it is forbidden unless it carries the evidence every skipped gate would have demanded.
  So the validator walks the ladder rung by rung and accumulates each rung's ``requires``.
- **COMPLETE is derived, never stored** (spec §18 decision 1). A committed projection
  asserting ``phase: COMPLETE`` is invalid, not merely stale: storing it reintroduces
  the post-merge mutation the whole model exists to remove.

Every rejection carries the uid, the attempted transition, and the failed clause — a
report that names only "illegal" gives an operator nothing to act on.

The **smoke-execution attestation** (#1602) — the record that a live-smoke test actually
RAN — is a different kind of evidence and lives apart, in :mod:`atdd.state.smoke_evidence`:
the tokens here are *derived from a commit* at merge-authority time, that one is *captured
by the test run itself*. ``evidence_for``'s ``smoke_evidence_artifact`` derivation is NOT
extended to read it: the merge authority may only read what is in the commit, and a run
artifact is not.

Dependency discipline: stdlib + ``atdd.state`` only. No provider, and in particular no
``external_refs`` is ever consulted for a lifecycle decision (I7, spec §8.2 rule 5).
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

#: The escapes the phase machine declares out of every rung. Off :data:`PHASE_LADDER` on
#: purpose — an escape orders against nothing, so it has no rung — but off the ladder is
#: not outside the model: each is entered through a wildcard policy entry, as
#: ``TOMBSTONED`` is. Before #1947 they had neither, so ``check_transition`` fell through
#: to its off-ladder branch and refused a *declared* edge as ``unknown_transition``.
#: One costs the operator token digest (I8: the approval reaches CI as a digest, never a
#: token) — the machine-readable form of the convention's one invariant about escapes, that
#: entering one is never autonomous. Deliberately NOT `reason_digest`: no projection field
#: carries an escape's reason, so `evidence_for` could never derive it and the edge would
#: stay as unwalkable as #1947 found it, merely better named. Give them a field, then tighten.
ESCAPES: FrozenSet[str] = frozenset({"BLOCKED", "OBSOLETE"})

#: Of those, the ones a phase may come back out of: ``BLOCKED`` is symmetric — entered by
#: operator decision and left by one — while ``OBSOLETE`` declares none and is terminal.
RESUMABLE_ESCAPES: FrozenSet[str] = frozenset({"BLOCKED"})

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
        # No `from`: an escape may be entered from any rung, so these are wildcard-source
        # entries like retirement below them — spread from ESCAPES rather than typed out, so
        # a newly declared escape cannot arrive with no entry (#1947's defect exactly). What
        # they require, and what they pointedly do not, is argued at :data:`ESCAPES`.
        *({"to": e, "requires": ["operator_token_digest"]} for e in sorted(ESCAPES)),
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
CLAUSE_ESCAPE_EVIDENCE = "escape_evidence"
CLAUSE_TERMINAL_PHASE = "terminal_phase"


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
    of evidence makes ``GREEN -> RED`` a legal shared claim, and the off-ladder edges are
    settled before the ladder is consulted at all, ranking being what would otherwise
    refuse a declared escape as ``unknown_transition`` (#1947).
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

    if before == after:
        return []  # a no-op phase-wise; other validators cover the rest of the diff

    if before in ESCAPES and before not in RESUMABLE_ESCAPES:
        return [Violation(
            uid, transition, CLAUSE_TERMINAL_PHASE,
            f"{before} is terminal: the phase machine declares no transition out of it, so "
            f"reopening is a new object, not a phase change",
        )]

    if after in ESCAPES:
        # No rung, so no walk to accumulate: the wildcard entry is all an escape owes.
        missing = [token for token in requires_for(before, after) or () if token not in have]
        if missing:
            return [Violation(
                uid, transition, CLAUSE_ESCAPE_EVIDENCE,
                f"entering {after} requires {sorted(missing)}; an escape is an operator "
                "decision and never an autonomous one",
            )]
        return []

    if before in RESUMABLE_ESCAPES:
        # Symmetric with entering it. The rung BLOCKED was entered from is not recoverable
        # from the diff — the escape kept no rank — so the resume is judged below like an
        # introduction at `after`, which is also what stops BLOCKED laundering a skip:
        # INIT -> BLOCKED -> GREEN owes everything INIT -> GREEN owed.
        if "operator_token_digest" not in have:
            violations.append(Violation(
                uid, transition, CLAUSE_ESCAPE_EVIDENCE,
                f"leaving {before} requires ['operator_token_digest']; an escape is entered "
                "by operator decision and left by one",
            ))
        before = None

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
        violations.append(Violation(
            uid, transition, CLAUSE_UNKNOWN_TRANSITION,
            f"no evidence-policy entry for {transition}",
        ))
        return violations

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

#: The separators a gate filename may join two phase names with. Both spellings are live
#: in-tree (``PLANNED-RED.yaml``, ``GREEN->SMOKE.yaml``); no phase name contains a ``-``.
_GATE_SEPARATORS: Tuple[str, ...] = ("->", "-")


def _gate_artifact_names() -> FrozenSet[str]:
    """Every filename stem that NAMES a gate, read off :data:`EVIDENCE_POLICY`.

    Derived, not typed out, so a rung added to the §6 table becomes an admissible
    filename by that edit alone; a second list would drift, and the drift would reach
    an operator as "the evidence is missing" rather than "the filename is unknown".

    One branch per entry shape: a concrete ``from``; the ``* -> TOMBSTONED`` wildcard,
    which has no ``from`` key and names one gate per rung; and the mint, whose ``from``
    is ``None``, named by its target phase alone. Absent and present-and-``None`` are
    different claims, hence the membership test.
    """
    names: Set[str] = set()
    for entry in EVIDENCE_POLICY["transitions"]:
        to_phase = str(entry["to"])
        if "from" not in entry:
            sources: Tuple[str, ...] = PHASE_LADDER
        elif entry["from"] is None:
            names.add(to_phase)
            continue
        else:
            sources = (str(entry["from"]),)
        names.update(
            f"{source}{sep}{to_phase}" for source in sources for sep in _GATE_SEPARATORS
        )
    return frozenset(names)


#: Resolved once at import: the stems an evidence artifact may be filed under.
_GATE_ARTIFACT_NAMES: FrozenSet[str] = _gate_artifact_names()


def _is_gate_evidence_artifact(path: str, uid: str) -> bool:
    """Is ``path`` the COMMITTED gate-evidence artifact of the object ``uid``?

    Only the two shapes ``govern_cli._evidence_at`` — the reader that OWNS the artifact
    — looks for: ``.atdd/evidence/<uid>/<gate>.yaml``, the per-gate shard, and
    ``.atdd/evidence/<uid>.yaml``, the flat form. Committed is the requirement, not an
    accident: evidence a merge cannot see is evidence the merge does not have (§6).
    Anything else under the prefix merely lives in the directory and attests to nothing
    (#1945: a bare ``startswith`` minted ``smoke_evidence_artifact`` — the sole
    requirement of BOTH ``GREEN->SMOKE`` and ``SMOKE->REFACTOR`` — from a ``README.md``).
    ``uid`` is load-bearing for the same reason: the derivation sees every path in the
    commit once per object in it, so an unscoped test let one object's honest artifact
    evidence every other object advancing beside it.

    NOT to be "aligned" with ``.atdd/smoke-evidence/<N>.yaml``, a near-miss of the name
    and a different artifact entirely: the #358 ratchet's local, gitignored,
    operator-TYPED stamp, written by ``atdd validate coder --smoke-required`` without
    running a test. Pointing this at it would either never fire (a gitignored path is
    never a changed path) or, if that ignore lifted, mint the token from a typed stamp
    — a brand-new false green. #1602 closed that class;
    ``test_evidence_token_derivation_paths.py`` keeps it closed.

    Shape, not content (#1945 decision 1): whether the file parses as a token list is
    the artifact's own schema to say, and the merge authority reads changed paths.
    """
    if not uid or not path.startswith(_MERGE_EVIDENCE_PREFIX):
        return False
    segments = path[len(_MERGE_EVIDENCE_PREFIX):].split("/")
    if len(segments) == 1:
        return segments[0] == f"{uid}.yaml"
    if len(segments) != 2 or segments[0] != uid:
        return False
    stem, _, extension = segments[1].rpartition(".")
    return extension == "yaml" and stem in _GATE_ARTIFACT_NAMES


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
    uid = str(document.get("uid") or "")
    if uid:
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
        elif _is_gate_evidence_artifact(path, uid):
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
