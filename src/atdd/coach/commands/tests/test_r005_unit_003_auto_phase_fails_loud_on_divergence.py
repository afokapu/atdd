# URN: test:govern-lifecycle:R005-UNIT-003-auto-phase-fails-loud-on-divergence
# Acceptance: acc:govern-lifecycle:R005-UNIT-003-auto-phase-fails-loud-on-divergence
# WMBT: wmbt:govern-lifecycle:R005
# Phase: RED
# Layer: application
# Assertion: behavioral
"""R005-UNIT-003 — ``atdd auto-phase`` reads ``objects.state`` and fails loud
when the store and the label disagree.

Pre-#1452 auto-phase read the ``atdd:<PHASE>`` *label*. A workflow with no
checkout stamped ``atdd:COMPLETE`` ~11s before auto-phase's Python could start,
auto-phase read that label, correctly concluded a terminal phase has no
auto-advance, and exited **0, green**. The reasoning was sound; the input was
the artifact it was supposed to be producing.

So two things are asserted, and they are not the same thing:

  1. the READ SOURCE moved to the store — proven by advancing on a store phase
     with no label present at all;
  2. SILENCE is no longer an acceptable outcome — a disagreement is a red build,
     because a green no-op is how 236 records accumulated unnoticed.

The regression fixture is #1434 itself: the issue whose purpose was to end this
desync, stamped ``atdd:COMPLETE`` with its own store honest at ``SMOKE``.

Issue #1452.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest

from atdd.coach.commands.auto_phase import resolve_pr_to_transition, run

pytestmark = [pytest.mark.coach]


@contextmanager
def _pr(issue_number: int, *, store: str | None, label: str | None):
    """A merged PR resolving to an issue with an explicit (store, label) pair."""
    resolution = {
        "issue_number": issue_number,
        "phase_label": label,
        "strategy": "api",
        "pr_data": {"number": 999},
        "issue_data": {"number": issue_number},
    }
    with patch(
        "atdd.coach.commands.auto_phase.PRManager.resolve_linked_issue",
        return_value=resolution,
    ), patch(
        "atdd.coach.commands.auto_phase.read_store_phase",
        return_value=store,
    ):
        yield


def test_divergence_reports_both_readings():
    """The #1434 signature must surface as a divergence, not a no-op."""
    with _pr(1434, store="SMOKE", label="COMPLETE"):
        result = resolve_pr_to_transition(999)

    assert result.action == "divergence", (
        "label=COMPLETE over a store at SMOKE must be a divergence. Pre-#1452 "
        f"this was action='noop' and exit 0. Got action={result.action!r}."
    )
    assert result.store_phase == "SMOKE"
    assert result.label_phase == "COMPLETE"
    assert result.current_phase == "SMOKE", "The store is the survivor."


def test_run_exits_non_zero_on_divergence():
    """A green build over a desynced issue is the failure mode being removed."""
    with _pr(1434, store="SMOKE", label="COMPLETE"):
        rc = run(999, dry_run=True)
    assert rc == 1, "auto-phase must FAIL the build on store/label divergence."


def test_divergence_does_not_transition():
    """A phase that cannot be trusted must not be acted on."""
    with _pr(1434, store="SMOKE", label="COMPLETE"), patch(
        "atdd.coach.commands.auto_phase.subprocess.run"
    ) as fake_run:
        rc = run(999)
    assert rc == 1
    assert not fake_run.called, (
        "auto-phase invoked a transition on a divergent issue; the phase is "
        "not trustworthy until the projection is repaired from the store."
    )


def test_advance_is_driven_by_the_store_not_the_label():
    """With no label at all, a store at SMOKE still yields SMOKE→REFACTOR.

    This is the read-source assertion: it cannot pass on the pre-#1452 code,
    which had nothing to read.
    """
    with _pr(1452, store="SMOKE", label=None):
        result = resolve_pr_to_transition(999)

    assert result.action == "transition"
    assert result.current_phase == "SMOKE"
    assert result.next_phase == "REFACTOR", (
        "The merge must advance exactly ONE legal phase, SMOKE→REFACTOR — "
        "never straight to COMPLETE, which the phase machine does not permit "
        f"from SMOKE. Got {result.next_phase!r}."
    )


def test_silent_store_falls_back_to_the_label():
    """An unknown work item is silent, not contradictory.

    Consumer repos and un-imported issues have no store row. Treating that as a
    disagreement would turn every merge in those repos red — a guard that fires
    on absence of evidence rather than evidence of a problem.
    """
    with _pr(340, store=None, label="RED"):
        result = resolve_pr_to_transition(999)

    assert result.action == "transition"
    assert result.current_phase == "RED"
    assert result.next_phase == "GREEN"
