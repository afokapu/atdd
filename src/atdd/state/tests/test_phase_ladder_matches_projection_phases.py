# URN: test:state-store:evidence:phase-ladder-matches-the-phase-machine
# Issue: #1602 (#1400)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""The evidence model's ladder IS the phase machine's linear spine (#1602).

Three copies of one truth: ``phase_machine.convention.yaml`` (the authored state
machine), :data:`atdd.state.projection.PHASES` (what a committed projection may
carry), and :data:`atdd.state.evidence.PHASE_LADDER` (what the legal-transition
gate ranks). They drifted — the ladder omitted ``REFACTOR`` while the other two
carried it — and the drift was silent until a projection actually moved: because
``SMOKE -> REFACTOR`` is the *only* legal way out of SMOKE, and ``REFACTOR`` had
no rung, every such advance was rejected ``unknown_transition``. A hard failure
on the one transition the lifecycle mandates.

So this is the tie. The ladder is not asserted against a hand-written literal —
it is walked out of the authored convention, which is what makes "the correct
position" a fact rather than this test's opinion.

``BLOCKED`` and ``OBSOLETE`` are escapes, not rungs: reachable from anywhere,
ordered relative to nothing, and so deliberately off the ladder. That is a
distinction the tests below make explicit rather than a gap they tolerate.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set

import pytest
import yaml

from atdd.state.evidence import (
    CLAUSE_MISSING_EVIDENCE,
    CLAUSE_UNKNOWN_TRANSITION,
    EVIDENCE_POLICY,
    PHASE_LADDER,
    PHASE_RANK,
    TOMBSTONED,
    check_transition,
)
from atdd.state.projection import PHASES

_REPO = Path(__file__).resolve().parents[4]
_CONVENTION = (
    _REPO / "src" / "atdd" / "coach" / "conventions" / "phase_machine.convention.yaml"
)

#: Off-spine phases: an escape is reachable from any rung and orders against none,
#: so it has no rank and belongs to no ladder walk (phase_machine.convention.yaml).
ESCAPES: Set[str] = {"BLOCKED", "OBSOLETE"}


@pytest.fixture(scope="module")
def phase_machine() -> Dict[str, dict]:
    if not _CONVENTION.is_file():
        pytest.fail(f"authored phase machine missing: {_CONVENTION}")
    document = yaml.safe_load(_CONVENTION.read_text(encoding="utf-8"))
    return document["phases"]


@pytest.fixture(scope="module")
def spine(phase_machine) -> List[str]:
    """The convention's linear chain: INIT, then each phase's one non-escape target."""
    chain = ["INIT"]
    seen = {"INIT"}
    while True:
        forward = [
            target
            for target in phase_machine[chain[-1]]["transitions_to"]
            if target not in ESCAPES
        ]
        if not forward:
            return chain
        assert len(forward) == 1, (
            f"{chain[-1]} forks to {forward}; the phase machine is no longer a linear "
            "spine and PHASE_LADDER's rank ordering has no single meaning"
        )
        assert forward[0] not in seen, f"the phase machine cycles back to {forward[0]}"
        seen.add(forward[0])
        chain.append(forward[0])


def test_the_ladder_is_the_phase_machines_spine(spine) -> None:
    """Every rung, in the authored order — REFACTOR between SMOKE and COMPLETE."""
    assert list(PHASE_LADDER) == spine, (
        "evidence.PHASE_LADDER has drifted from phase_machine.convention.yaml; a phase "
        "off the ladder has no rank, so every transition through it is rejected "
        "unknown_transition"
    )


def test_every_projectable_phase_has_a_rung_or_is_an_escape() -> None:
    """No phase a committed projection may carry falls off the ladder unaccounted for."""
    unranked = [phase for phase in PHASES if phase not in PHASE_RANK]
    assert set(unranked) == ESCAPES, (
        f"projection.PHASES carries {sorted(set(unranked) - ESCAPES)}, which the evidence "
        "model can neither rank nor gate"
    )


def test_complete_is_the_one_rung_that_is_never_projected() -> None:
    """COMPLETE is derived from merge-to-main (spec §18 decision 1), so it is ranked
    but never stored; every other rung is both."""
    assert set(PHASE_LADDER) - set(PHASES) == {"COMPLETE"}


def test_every_adjacent_rung_has_an_evidence_policy_entry() -> None:
    """A rung with no policy entry is a gate that rejects rather than gates.

    Walking the ladder is what turns a jump into the gates it skipped, so a missing
    entry does not fail open — it fails the whole transition ``unknown_transition``.
    """
    entries = {
        (entry.get("from"), entry["to"])
        for entry in EVIDENCE_POLICY["transitions"]
        if "from" in entry
    }
    missing = [
        (lower, upper)
        for lower, upper in zip(PHASE_LADDER, PHASE_LADDER[1:])
        if (lower, upper) not in entries
    ]
    assert not missing, f"the evidence policy has no entry for the ladder rung(s) {missing}"


def test_no_policy_entry_names_a_transition_the_ladder_does_not_have() -> None:
    """The table states rungs and the mint and retirement — nothing else.

    An entry spanning two rungs (the old ``SMOKE -> COMPLETE``) reads as a single gate
    while the ladder walks it as two, and the two answers disagree about what evidence
    the jump owes.
    """
    rungs = set(zip(PHASE_LADDER, PHASE_LADDER[1:]))
    stray = [
        (entry.get("from"), entry["to"])
        for entry in EVIDENCE_POLICY["transitions"]
        if "from" in entry
        and entry["to"] != TOMBSTONED
        and (entry.get("from"), entry["to"]) not in rungs
        and not (entry.get("from") is None and entry["to"] == PHASE_LADDER[0])
    ]
    assert not stray, f"evidence-policy entr(ies) {stray} are not rungs of {list(PHASE_LADDER)}"


def test_smoke_to_refactor_is_gated_rather_than_rejected() -> None:
    """The consequence the constants exist for, asserted on the validator itself.

    Pre-#1602 this returned ``unknown_transition`` whatever the commit carried, so a
    SMOKE issue could not advance at all. It must now behave like any other rung: it
    passes on its evidence and fails, nameably, without it.
    """
    admitted = check_transition("uid", "SMOKE", "REFACTOR", ["smoke_evidence_artifact"])
    assert admitted == [], (
        f"SMOKE->REFACTOR is the only legal exit from SMOKE and it was rejected: {admitted}"
    )

    refused = check_transition("uid", "SMOKE", "REFACTOR", [])
    assert [violation.clause for violation in refused] == [CLAUSE_MISSING_EVIDENCE]
    assert CLAUSE_UNKNOWN_TRANSITION not in {violation.clause for violation in refused}
