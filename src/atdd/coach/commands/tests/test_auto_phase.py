"""
Unit tests for `atdd auto-phase`.

Issue #355: auto-transition the parent atdd-issue's phase when its PR merges.

The pure helper takes a PR number, resolves the parent issue, reads its
current phase label, and returns the next phase per the state machine in
CLAUDE.md (RED→GREEN, GREEN→SMOKE, SMOKE→REFACTOR, REFACTOR→COMPLETE).

Phases that are terminal or have no defined post-merge advance return a
no-op. PRs without a closing-keyword reference also no-op.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from atdd.coach.commands.auto_phase import (
    AutoPhaseResult,
    compute_next_phase,
    resolve_pr_to_transition,
)

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# compute_next_phase — pure state-machine lookup
# ---------------------------------------------------------------------------


def test_compute_next_phase_red_to_green():
    assert compute_next_phase("RED") == "GREEN"


def test_compute_next_phase_green_to_smoke():
    assert compute_next_phase("GREEN") == "SMOKE"


def test_compute_next_phase_smoke_to_refactor():
    assert compute_next_phase("SMOKE") == "REFACTOR"


def test_compute_next_phase_refactor_to_complete():
    assert compute_next_phase("REFACTOR") == "COMPLETE"


def test_compute_next_phase_complete_is_terminal():
    assert compute_next_phase("COMPLETE") is None


def test_compute_next_phase_obsolete_is_terminal():
    assert compute_next_phase("OBSOLETE") is None


def test_compute_next_phase_init_no_advance_on_merge():
    # INIT/PLANNED are pre-implementation phases; merging a PR while in
    # those states is unusual but should not advance — operator must
    # transition manually.
    assert compute_next_phase("INIT") is None


def test_compute_next_phase_planned_no_advance_on_merge():
    assert compute_next_phase("PLANNED") is None


def test_compute_next_phase_blocked_no_advance():
    assert compute_next_phase("BLOCKED") is None


def test_compute_next_phase_none_input_returns_none():
    assert compute_next_phase(None) is None


def test_compute_next_phase_unknown_phase_returns_none():
    assert compute_next_phase("BOGUS") is None


# ---------------------------------------------------------------------------
# resolve_pr_to_transition — PR resolution + state-machine advance
# ---------------------------------------------------------------------------


def _resolution(issue_number: int, phase: str | None) -> dict:
    return {
        "issue_number": issue_number,
        "phase_label": phase,
        "strategy": "api",
        "pr_data": {"number": 999},
        "issue_data": {"number": issue_number},
    }


def test_resolve_pr_returns_transition_for_red_issue():
    with patch(
        "atdd.coach.commands.auto_phase.PRManager.resolve_linked_issue",
        return_value=_resolution(340, "RED"),
    ):
        result = resolve_pr_to_transition(350)
    assert isinstance(result, AutoPhaseResult)
    assert result.issue_number == 340
    assert result.current_phase == "RED"
    assert result.next_phase == "GREEN"
    assert result.action == "transition"


def test_resolve_pr_returns_noop_for_terminal_issue():
    with patch(
        "atdd.coach.commands.auto_phase.PRManager.resolve_linked_issue",
        return_value=_resolution(340, "COMPLETE"),
    ):
        result = resolve_pr_to_transition(350)
    assert result.issue_number == 340
    assert result.current_phase == "COMPLETE"
    assert result.next_phase is None
    assert result.action == "noop"


def test_resolve_pr_returns_noop_when_no_linked_issue():
    with patch(
        "atdd.coach.commands.auto_phase.PRManager.resolve_linked_issue",
        return_value=None,
    ):
        result = resolve_pr_to_transition(350)
    assert result.issue_number is None
    assert result.action == "noop"
    assert "no linked issue" in (result.reason or "").lower()


def test_resolve_pr_returns_noop_when_phase_label_missing():
    with patch(
        "atdd.coach.commands.auto_phase.PRManager.resolve_linked_issue",
        return_value=_resolution(340, None),
    ):
        result = resolve_pr_to_transition(350)
    assert result.issue_number == 340
    assert result.current_phase is None
    assert result.action == "noop"
