"""Fixture-based tests for ``atdd.integrations.github.issue_state`` (no live API).

``transition_phase`` swaps the ``atdd:<phase>`` label over REST and does
nothing else. #1051 decommissioned the Projects v2 board this used to sync in
the same call, and #1761 removed the tests that still asserted the sync — they
imported a ``projects_v2`` module deleted from the package, so this whole file
had been failing to import.
"""
from __future__ import annotations

import json

from atdd.integrations.github import _gh, issue_state

ISSUE = 891


def _recording_run_gh(recorder, labels):
    def fake(args, *, token=None, input_text=None, timeout=30):
        recorder.append(list(args))
        if args[:2] == ["issue", "view"]:
            return json.dumps(labels)
        return ""
    return fake


def test_read_phase_extracts_atdd_label(monkeypatch):
    monkeypatch.setattr(
        _gh, "run_gh",
        _recording_run_gh([], ["atdd-issue", "atdd:GREEN"]),
    )
    assert issue_state.read_phase(ISSUE) == "GREEN"


def test_transition_phase_swaps_the_label(monkeypatch):
    """The stale phase label comes off and the new one goes on — REST only."""
    calls = []
    monkeypatch.setattr(
        _gh, "run_gh",
        _recording_run_gh(calls, ["atdd-issue", "atdd:RED"]),
    )

    issue_state.transition_phase(ISSUE, "COMPLETE")

    edit_calls = [c for c in calls if c[:2] == ["issue", "edit"]]
    assert ["issue", "edit", str(ISSUE), "--remove-label", "atdd:RED"] in edit_calls
    assert ["issue", "edit", str(ISSUE), "--add-label", "atdd:COMPLETE"] in edit_calls
    # No board call rides along: every command is `gh issue …`, never `gh api graphql`.
    assert all(c[0] == "issue" for c in calls), calls


def test_transition_phase_skips_redundant_remove(monkeypatch):
    """Re-applying the same phase does not remove-then-add the live label."""
    calls = []
    monkeypatch.setattr(
        _gh, "run_gh",
        _recording_run_gh(calls, ["atdd-issue", "atdd:GREEN"]),
    )

    issue_state.transition_phase(ISSUE, "GREEN")

    assert ["issue", "edit", str(ISSUE), "--remove-label", "atdd:GREEN"] not in calls
