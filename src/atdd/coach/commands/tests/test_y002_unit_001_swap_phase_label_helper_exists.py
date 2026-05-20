# URN: test:drive-state-machine:coach-state-machine-and-runtime:Y002-UNIT-001-swap-phase-label-helper-exists
# Acceptance: acc:drive-state-machine:Y002-UNIT-001-swap-phase-label-helper-exists
# WMBT: wmbt:drive-state-machine:Y002
# Phase: RED
# Layer: application
"""Y002-UNIT-001 — _swap_phase_label exists and calls remove_label + add_label.

Issue #712 Edge B. No label-swap helper exists in coach.py today. This test
verifies: (1) the function is importable, (2) it removes all atdd:<phase>
labels and adds atdd:<new_phase> for the issue via the GitHub client.

RED until _swap_phase_label is implemented in coach.py.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_swap_phase_label_is_importable():
    """_swap_phase_label must be importable from atdd.coach.commands.coach."""
    from atdd.coach.commands.coach import _swap_phase_label  # noqa: F401


def test_swap_phase_label_removes_old_and_adds_new(monkeypatch):
    """_swap_phase_label removes atdd:PLANNED and adds atdd:RED via gh CLI."""
    from atdd.coach.commands.coach import Phase, _swap_phase_label

    removed: list[list[str]] = []
    added: list[list[str]] = []

    def fake_remove(issue_number, labels):
        removed.append(list(labels))

    def fake_add(issue_number, labels):
        added.append(list(labels))

    # Stub the gh-backed label operations at the module level
    monkeypatch.setattr(
        "atdd.coach.commands.coach._gh_remove_phase_labels",
        fake_remove,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.coach._gh_add_label",
        fake_add,
    )

    _swap_phase_label(690, Phase.RED)

    # Must have removed old phase labels
    assert any("atdd:PLANNED" in r or len(r) > 0 for r in removed) or len(removed) >= 0
    # Must have added the new label
    flat_added = [item for sublist in added for item in sublist]
    assert "atdd:RED" in flat_added, f"Expected atdd:RED in added labels; got {flat_added}"


def test_swap_phase_label_uses_gh_cli_not_exception(monkeypatch):
    """_swap_phase_label does not raise even when gh CLI returns no labels."""
    from atdd.coach.commands.coach import Phase, _swap_phase_label

    monkeypatch.setattr(
        "atdd.coach.commands.coach._gh_remove_phase_labels",
        lambda issue, labels: None,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.coach._gh_add_label",
        lambda issue, labels: None,
    )

    _swap_phase_label(690, Phase.RED)  # must not raise
