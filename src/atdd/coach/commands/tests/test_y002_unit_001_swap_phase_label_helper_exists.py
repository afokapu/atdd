# URN: test:drive-state-machine:coach-state-machine-and-runtime:Y002-UNIT-001-swap-phase-label-helper-exists
# Acceptance: acc:drive-state-machine:Y002-UNIT-001-swap-phase-label-helper-exists
# WMBT: wmbt:drive-state-machine:Y002
# Phase: RED
# Layer: application
"""Y002-UNIT-001 — _swap_phase_label exists and calls remove_label + add_label.

Issue #712 Edge B. The coach state machine advances its internal phase but left
the GitHub ``atdd:<phase>`` label stale; ``_swap_phase_label`` closes that gap.
This test verifies: (1) the function is importable, (2) the issue ends up with
its old ``atdd:<phase>`` labels removed and ``atdd:<new_phase>`` added.

#1452 moved the SEAM, not the acceptance. ``_swap_phase_label`` used to shell
out through module-level ``_gh_remove_phase_labels`` / ``_gh_add_label`` shims,
which made it a second independent author of the phase label — it stamped the
projection while ``objects.state`` stood still. It now delegates to
``IssueManager.update``, the store-first authoritative writer, so the assertions
below observe ``client.remove_label`` / ``client.add_label`` (exactly the
``remove_label``/``add_label`` calls the Y002 acceptance names) instead of the
deleted gh shims.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.platform]


def test_swap_phase_label_is_importable():
    """_swap_phase_label must be importable from atdd.coach.commands.coach."""
    from atdd.coach.commands.coach import _swap_phase_label  # noqa: F401


def _fake_manager(current_labels: list[str]):
    """An IssueManager whose gates pass, exposing a recording GitHub client."""
    client = MagicMock()
    manager = MagicMock()
    manager.update.side_effect = lambda issue_id, status: _apply(
        manager, client, int(issue_id), current_labels, status
    )
    return manager, client


def _apply(manager, client, issue_number, current_labels, status):
    """Mimic IssueManager.update's store-then-project sequence."""
    phase_labels = [
        l for l in current_labels if l.startswith("atdd:") and l != "atdd-issue"
    ]
    if phase_labels:
        client.remove_label(issue_number, phase_labels)
    client.add_label(issue_number, [f"atdd:{status}"])
    return 0


def test_swap_phase_label_removes_old_and_adds_new():
    """_swap_phase_label removes atdd:PLANNED and adds atdd:RED."""
    from atdd.coach.commands.coach import Phase, _swap_phase_label

    manager, client = _fake_manager(["atdd-issue", "atdd:PLANNED"])
    with patch("atdd.coach.commands.issue.IssueManager", return_value=manager):
        rc = _swap_phase_label(690, Phase.RED)

    assert rc == 0
    removed = [list(c.args[1]) for c in client.remove_label.call_args_list]
    added = [list(c.args[1]) for c in client.add_label.call_args_list]

    flat_removed = [item for sublist in removed for item in sublist]
    assert "atdd:PLANNED" in flat_removed, (
        f"Expected atdd:PLANNED to be removed; got {flat_removed}"
    )
    flat_added = [item for sublist in added for item in sublist]
    assert "atdd:RED" in flat_added, (
        f"Expected atdd:RED in added labels; got {flat_added}"
    )
    # No other phase label survives the swap.
    assert flat_added == ["atdd:RED"]


def test_swap_phase_label_routes_through_the_authoritative_writer():
    """#1452: the label must be written by IssueManager.update, never raw gh.

    A second writer is the defect this issue removes. Asserting the delegation
    directly is what stops the raw-gh shim being reintroduced "just here".
    """
    from atdd.coach.commands.coach import Phase, _swap_phase_label

    manager, _ = _fake_manager(["atdd:PLANNED"])
    with patch("atdd.coach.commands.issue.IssueManager", return_value=manager):
        _swap_phase_label(690, Phase.RED)

    manager.update.assert_called_once_with(issue_id="690", status="RED")


def test_swap_phase_label_does_not_raise_on_failure():
    """A refused or failed transition surfaces as non-zero, never an exception."""
    from atdd.coach.commands.coach import Phase, _swap_phase_label

    manager = MagicMock()
    manager.update.side_effect = RuntimeError("gh unavailable")
    with patch("atdd.coach.commands.issue.IssueManager", return_value=manager):
        rc = _swap_phase_label(690, Phase.RED)  # must not raise

    assert rc == 1
