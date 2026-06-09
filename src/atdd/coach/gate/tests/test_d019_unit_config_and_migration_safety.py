# URN: test:govern-lifecycle:enforcing-phase-transition-gate:D019-UNIT-001-planned-to-red-gated-by-default-config-toggles
# Acceptance: acc:govern-lifecycle:D019-UNIT-001-planned-to-red-gated-by-default-config-toggles
# Acceptance: acc:govern-lifecycle:D019-UNIT-002-empty-registry-and-ungated-transition-proceed
# WMBT: wmbt:govern-lifecycle:D019
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""D019 — config-driven gating AND empty-registry no-op (migration safety).

Advisory -> blocking is behavior-changing. Two guards keep the keystone inert
until #958/#1017 register real checks:
  1. is_transition_gated(config, from, to): PLANNED->RED gated by default,
     operator-toggleable via .atdd/config.yaml gate.transitions; an ungated
     transition proceeds without consulting any check.
  2. an EMPTY registry: a gated transition with zero registered checks proceeds.
The conjunction is the proof that NO existing transition can start failing.

RED state: there is no atdd.coach.gate module.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.gate.decision import (
    GateContext,
    evaluate_transition_gate,
    is_transition_gated,
)
from atdd.coach.gate.registry import GateRegistry

pytestmark = [pytest.mark.platform]


def test_planned_to_red_gated_by_default_config_toggles():
    """D019-UNIT-001: default gates PLANNED->RED; config can disable/enable transitions."""
    empty_config: dict = {}

    # Default: PLANNED->RED is gated, an unlisted transition is not.
    assert is_transition_gated(empty_config, "PLANNED", "RED") is True
    assert is_transition_gated(empty_config, "GREEN", "SMOKE") is False

    # Operator override flips both.
    override = {
        "gate": {
            "transitions": {
                "PLANNED->RED": False,
                "GREEN->SMOKE": True,
            }
        }
    }
    assert is_transition_gated(override, "PLANNED", "RED") is False
    assert is_transition_gated(override, "GREEN", "SMOKE") is True


def test_empty_registry_and_ungated_transition_proceed(tmp_path: Path):
    """D019-UNIT-002: MIGRATION SAFETY — gated-but-unregistered and ungated both proceed."""
    empty_registry = GateRegistry()
    config = {"gate": {"transitions": {"PLANNED->RED": True}}}

    gated_ctx = GateContext(
        issue_number=1020, from_phase="PLANNED", to_phase="RED", worktree=tmp_path
    )
    ungated_ctx = GateContext(
        issue_number=1020, from_phase="GREEN", to_phase="SMOKE", worktree=tmp_path
    )

    # Gated transition, but the registry is empty -> no existing transition fails.
    gated_outcome = evaluate_transition_gate(empty_registry, config, gated_ctx)
    assert gated_outcome.proceed is True
    assert gated_outcome.results == ()

    # Ungated transition -> proceeds without consulting any check.
    ungated_outcome = evaluate_transition_gate(empty_registry, config, ungated_ctx)
    assert ungated_outcome.proceed is True
    assert ungated_outcome.results == ()
