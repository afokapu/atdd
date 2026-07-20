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

from contextlib import contextmanager
from unittest.mock import patch

import pytest

from atdd.coach.commands.auto_phase import (
    AutoPhaseResult,
    compute_next_phase,
    resolve_pr_to_transition,
    run,
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


@contextmanager
def _pr_at(issue_number: int, *, store: str | None, label: str | None):
    """Drive resolution with an explicit (store, label) pair.

    #1452: the phase now comes from ``objects.state``, so the store read is
    stubbed alongside the PR resolution. Stubbing it is also what keeps these
    tests hermetic — an unpatched ``read_store_phase`` reads the developer's
    live state.sqlite and the assertions become a function of local data.
    """
    with patch(
        "atdd.coach.commands.auto_phase.PRManager.resolve_linked_issue",
        return_value=_resolution(issue_number, label),
    ), patch(
        "atdd.coach.commands.auto_phase.read_store_phase",
        return_value=store,
    ):
        yield


def test_resolve_pr_returns_transition_for_red_issue():
    with _pr_at(340, store="RED", label="RED"):
        result = resolve_pr_to_transition(350)
    assert isinstance(result, AutoPhaseResult)
    assert result.issue_number == 340
    assert result.current_phase == "RED"
    assert result.next_phase == "GREEN"
    assert result.action == "transition"


def test_resolve_pr_returns_noop_for_terminal_issue():
    with _pr_at(340, store="COMPLETE", label="COMPLETE"):
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


def test_resolve_pr_returns_noop_when_phase_is_unknown_everywhere():
    """Neither the store nor the label knows this issue — nothing to advance."""
    with _pr_at(340, store=None, label=None):
        result = resolve_pr_to_transition(350)
    assert result.issue_number == 340
    assert result.current_phase is None
    assert result.action == "noop"


# ---------------------------------------------------------------------------
# #1452 — the store is authoritative, and divergence is loud
# ---------------------------------------------------------------------------


def test_resolve_pr_reads_the_store_not_the_label():
    """The store drives the advance even when a label is present and agrees.

    The pre-#1452 code read ``phase_label``. This asserts the read source moved:
    with the label absent entirely, a store at SMOKE still yields SMOKE→REFACTOR.
    """
    with _pr_at(340, store="SMOKE", label=None):
        result = resolve_pr_to_transition(350)
    assert result.current_phase == "SMOKE"
    assert result.next_phase == "REFACTOR"
    assert result.action == "transition"


def test_resolve_pr_flags_divergence_instead_of_noopping():
    """The #1434 signature: label stamped COMPLETE, store honest at SMOKE.

    Pre-#1452 this returned ``action="noop"`` with reason "phase COMPLETE has no
    auto-advance" and exit 0 — the silence that let 236 records drift. It must
    now surface as a divergence carrying BOTH readings.
    """
    with _pr_at(1434, store="SMOKE", label="COMPLETE"):
        result = resolve_pr_to_transition(350)
    assert result.action == "divergence"
    assert result.store_phase == "SMOKE"
    assert result.label_phase == "COMPLETE"
    assert result.next_phase is None
    # The store is the survivor — it is what current_phase reports.
    assert result.current_phase == "SMOKE"
    assert "objects.state=SMOKE" in (result.reason or "")
    assert "label=atdd:COMPLETE" in (result.reason or "")


def test_resolve_pr_does_not_flag_divergence_when_store_is_silent():
    """A store that has never seen the issue is silent, not contradictory.

    Consumer repos and un-imported work items must not turn every merge red, so
    an unknown store falls back to the label rather than failing the build.
    """
    with _pr_at(340, store=None, label="RED"):
        result = resolve_pr_to_transition(350)
    assert result.action == "transition"
    assert result.current_phase == "RED"
    assert result.next_phase == "GREEN"


def test_run_exits_non_zero_on_divergence():
    """`atdd auto-phase` must FAIL the build, not pass green (#1452)."""
    with _pr_at(1434, store="SMOKE", label="COMPLETE"):
        rc = run(350, dry_run=True)
    assert rc == 1, "auto-phase must exit non-zero when store and label disagree"


def test_run_divergence_does_not_transition():
    """A divergent issue must not be advanced — the phase is not trustworthy."""
    with _pr_at(1434, store="SMOKE", label="COMPLETE"), patch(
        "atdd.coach.commands.auto_phase.subprocess.run"
    ) as fake_run:
        rc = run(350)
    assert rc == 1
    fake_run.assert_not_called()
