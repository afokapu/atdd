# URN: test:govern-lifecycle:enforce-lab-evidence:E083-SMOKE-001-real-transition-refused-then-allowed
# Acceptance: acc:govern-lifecycle:E083-SMOKE-001-real-transition-refused-then-allowed
# WMBT: wmbt:govern-lifecycle:E083
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E083-SMOKE-001 — the real transition, refused on an unfilled lab and allowed once filled.

Everything else in E083 is asserted against a seam: the pure evaluator, or a fresh
``GateRegistry`` handed to ``evaluate_transition_gate`` directly. This file is the
only proof the seams are CONNECTED — that the check the dispatch registers is the
check that decides, reading the body the store actually holds.

BOTH DIRECTIONS, and the second is the one that matters. A gate asserted only on its
refusal can be satisfied by a check that refuses everything, and a gate nobody can
pass is indistinguishable from a broken lifecycle. So the same issue, with the same
number, on the same edge, must flip to proceeding when — and only when — its lab is
filled in.

MARKED ``live_smoke``: the acceptance declares an execution kind, so the run itself
writes the attestation (see smoke_execution_check.py). Nothing here is stubbed
except the absence of a network: the store is real, the config is real, and the
decision comes from ``evaluate_transition_gate`` rather than from calling the check
by hand.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_EDGE_GATED = {"gate": {"transitions": {"INIT->PLANNED": True}}}

_FILLED_LAB = """## Lab

### Hypothesis

A required, gated `## Lab` changes what gets built, and can be enforced at INIT's exit.

### Setup

Retrospective over the four issues carrying a lab, plus a prototype driven through
every state in a disposable repo.

### Measured result

Of four labs, one was run. Making the section schema-required costs 394 issues.

### What it changed about the plan

Inverted it: the schema change is out, the edge check is in.
"""

_UNFILLED_LAB = """## Lab

### Hypothesis

(the premise this issue rests on, stated so it could be false)

### Setup

(how it was tested against the real system)

### Measured result

_To fill before INIT -> PLANNED._

### What it changed about the plan

_To fill._
"""


def _decide(worktree: Path, issue_number: int):
    """Ask the REAL registry+dispatch what it thinks of this transition."""
    from atdd.coach.gate.decision import GateContext, evaluate_transition_gate
    from atdd.coach.gate.registry import GateRegistry

    try:
        from atdd.coach.gate.registrations import register_lab_evidence_check
    except ImportError:  # pragma: no cover - the RED state
        pytest.fail(
            "registrations.register_lab_evidence_check not implemented yet — "
            "#1950 GREEN; INIT->PLANNED has no evidence check to connect."
        )

    registry = GateRegistry()
    register_lab_evidence_check(registry)
    ctx = GateContext(
        issue_number=issue_number, from_phase="INIT", to_phase="PLANNED", worktree=worktree
    )
    return evaluate_transition_gate(registry, _EDGE_GATED, ctx)


def _seed_issue(control_root: Path, issue_number: int, lab: str) -> None:
    """Put a real work item carrying *lab* into a real State Store.

    Same seeding path E019-SMOKE-001 uses — the shipped writer against a real
    migrated store, not a fixture shaped like one.
    """
    from atdd.state.db import connect, init_state_store
    from atdd.state.work_item_writer import create_work_item

    body = f"# Seeded issue\n\n## Scope\n\nstuff\n\n{lab}\n## Phases\n"
    conn = connect(init_state_store(start=control_root))
    try:
        create_work_item(
            conn,
            f"seeded-{issue_number}",
            state="INIT",
            data={"title": "Seeded issue", "type": "implementation", "body": body},
            github_number=issue_number,
        )
    finally:
        conn.close()


@pytest.mark.smoke
@pytest.mark.live_smoke
def test_real_transition_is_refused_while_the_lab_is_unfilled(tmp_path: Path):
    control = tmp_path / "control"
    control.mkdir(parents=True, exist_ok=True)
    _seed_issue(control, 424242, _UNFILLED_LAB)

    outcome = _decide(control, 424242)

    assert not outcome.proceed, "an unfilled lab must refuse INIT->PLANNED"
    reported = " | ".join(
        b.message for b in getattr(outcome, "blockers", ()) if getattr(b, "message", None)
    )
    for name in ("Measured result", "What it changed about the plan"):
        assert name in reported, (
            f"the refusal must name `### {name}` so the operator knows what to fill; "
            f"got {reported!r}"
        )


@pytest.mark.smoke
@pytest.mark.live_smoke
def test_real_transition_proceeds_once_the_lab_is_filled(tmp_path: Path):
    """The direction that proves the gate is passable, not merely strict."""
    control = tmp_path / "control"
    control.mkdir(parents=True, exist_ok=True)
    _seed_issue(control, 424243, _FILLED_LAB)

    outcome = _decide(control, 424243)

    assert outcome.proceed, (
        "a filled lab must satisfy the gate; a gate reachable only through --force "
        "is a rubber stamp"
    )
