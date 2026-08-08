# URN: test:govern-lifecycle:enforcing-phase-transition-gate:R011-UNIT-002-gated-edge-with-no-registered-check-refuses-as-could-not-check
# Acceptance: acc:govern-lifecycle:R011-UNIT-002-gated-edge-with-no-registered-check-refuses-as-could-not-check
# WMBT: wmbt:govern-lifecycle:R011
# Phase: RED
# Layer: unit
# Assertion: behavioral
# Purpose: an unpopulated registry on a gated edge is an error condition, not a green light — while the PURE decision function keeps the empty-registry no-op D019-UNIT-002 pins as migration safety
"""R011-UNIT-002 — a gated edge with no check REFUSES, as COULD_NOT_CHECK.

Root cause fact two (#1619): an unpopulated registry is read as permission to
proceed in TWO places, not the one the issue body names.

  A. ``IssueLifecycle._transition_gate`` returns 0 outright on
     ``GATE_REGISTRY.is_empty()``.
  B. ``decision.evaluate_transition_gate`` returns ``proceed=True`` whenever
     ``checks_for(from, to)`` is empty.

A short-circuits on a GLOBALLY empty registry; B proceeds whenever THIS EDGE
carries no check. Closing only A leaves the bypass open for the case that
matters — a registry populated for other edges but not the one being crossed.

WHY THE REFUSAL LIVES AT THE SEAM AND NOT IN ``decision.py``. B is a landed
acceptance: ``acc:govern-lifecycle:D019-UNIT-002-empty-registry-and-ungated-
transition-proceed`` REQUIRES a gated-but-unregistered edge to proceed, and
``plan/govern_lifecycle/D019.yaml`` states that conjunction as #1020's
migration-safety proof. The pure function cannot tell a migration-era empty
registry from a deleted registrar, because it does not know whether registration
ran. The seam does — it performs the registration — so the refusal belongs there.
This test asserts BOTH halves, so a fix that closes the bypass by breaking D019
fails here rather than in a surprised sibling.

The verdict is the existing ``COULD_NOT_CHECK`` (#1719/C013), not a new refusal
mode: "the registry holds no check for this gated edge" IS an observation that
could not be performed. It already refuses, and it is already reported apart from
``failures`` because the operator's remedy differs — make the check able to look,
rather than fix the work.

RED state: ``atdd.coach.gate.enforcement`` does not exist.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.gate.decision import (
    GateContext,
    GateVerdict,
    evaluate_transition_gate,
)
from atdd.coach.gate.registry import GateRegistry

pytestmark = [pytest.mark.platform]

_ISSUE = 999012

# INIT->PLANNED is the honest fixture for "gated, but no check covers it": it is
# deliberately absent from registrations._CANDIDATE_TRANSITIONS ("creating the
# plan is not an operator-reserved sign-off"), so it stays unregistered even
# AFTER the seam has run every production registrar. That is the same shape a
# deleted registrar leaves behind, reached without monkeypatching the registrars.
_UNCOVERED_EDGE = ("INIT", "PLANNED")
_GATED_CONFIG = {"gate": {"transitions": {"INIT->PLANNED": True}}}


def _ctx(worktree: Path) -> GateContext:
    return GateContext(
        issue_number=_ISSUE,
        from_phase=_UNCOVERED_EDGE[0],
        to_phase=_UNCOVERED_EDGE[1],
        worktree=worktree,
    )


def test_seam_refuses_a_gated_edge_no_check_covers(tmp_path: Path):
    """R011-UNIT-002: refuses, with a reason an operator can act on."""
    from atdd.coach.gate.enforcement import enforce_transition_gate

    registry = GateRegistry()
    outcome = enforce_transition_gate(_GATED_CONFIG, _ctx(tmp_path), registry=registry)

    assert outcome.proceed is False, (
        "a gated edge whose registry holds no check after registration ran is an "
        "error condition, not a green light"
    )

    # Reported as unobservable, NOT as a failure: the remedy is to make the gate
    # able to look, not to fix the work. Counting `failures` alone would render
    # this as 'blocked by 0 gate check(s)' — the vacuous refusal #1719 removed.
    assert len(outcome.unobservable) == 1, (
        f"expected exactly one could-not-check result; got "
        f"{[(r.gate_id, r.verdict) for r in outcome.results]}"
    )
    assert outcome.failures == (), "nothing OBSERVED a violation here"

    unregistered = outcome.unobservable[0]
    assert unregistered.verdict is GateVerdict.COULD_NOT_CHECK
    assert unregistered in outcome.blockers

    # The refusal must name the edge. A refusal an operator cannot act on is only
    # marginally better than the vacuous pass it replaces.
    message = unregistered.message
    assert "INIT" in message and "PLANNED" in message, (
        f"the message must name the unregistered edge; got: {message!r}"
    )


def test_pure_decision_function_keeps_the_d019_empty_registry_contract(tmp_path: Path):
    """R011-UNIT-002: D019-UNIT-002 is not collateral damage.

    The same empty registry, config and context, through the PURE function, must
    still proceed. If this ever fails, the fix has been pushed one layer too deep
    and #1020's shipped migration-safety proof has been rewritten in passing.

    HONEST SCOPE: this is a REGRESSION GUARD and passes in RED by construction —
    it pins behaviour that must NOT change. It is stated here, beside the refusal
    it constrains, so the two halves of Decision 3 cannot drift apart.
    """
    empty_registry = GateRegistry()
    outcome = evaluate_transition_gate(empty_registry, _GATED_CONFIG, _ctx(tmp_path))

    assert outcome.proceed is True
    assert outcome.results == ()
