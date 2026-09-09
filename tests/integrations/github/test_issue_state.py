"""Fixture-based tests for ``atdd.integrations.github.issue_state`` (no live API).

Covers ``transition_phase``: swapping the ``atdd:<phase>`` label, which since
#1051 (``35ae50c0``) is the whole of what it does — "No Projects v2 board write",
per its own docstring.

This file previously asserted the #882 guarantee that one call swapped the label
AND synced a Projects v2 board. That collaborator was deleted with the substrate,
and its ``PROJECT_TOKEN`` env with it, but these tests were left importing both —
so the module raised at import and took the whole configured suite's collection
down with it (#1868). The label assertions were still correct and are kept; the
board-sync ones described behaviour that no longer exists and are gone.

#1761 reached the same conclusion independently and additionally asserted the
absence of any `gh api graphql` call; that assertion is kept here.
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


def test_transition_phase_swaps_the_phase_label(monkeypatch):
    """The stale label is removed and the target added, in one call."""
    calls = []
    monkeypatch.setattr(
        _gh, "run_gh",
        _recording_run_gh(calls, ["atdd-issue", "atdd:RED"]),
    )

    issue_state.transition_phase(ISSUE, "COMPLETE")

    edit_calls = [c for c in calls if c[:2] == ["issue", "edit"]]
    assert ["issue", "edit", str(ISSUE), "--remove-label", "atdd:RED"] in edit_calls
    assert ["issue", "edit", str(ISSUE), "--add-label", "atdd:COMPLETE"] in edit_calls
    # No board call rides along: every command is `gh issue ...`, never
    # `gh api graphql`. Kept from #1763, which asserted the absence directly
    # rather than inferring it from the presence of the label edits.
    assert all(c[0] == "issue" for c in calls), calls


def test_transition_phase_leaves_unrelated_labels_alone(monkeypatch):
    """Only ``atdd:<phase>`` labels are touched — ``atdd-issue`` is not a phase."""
    calls = []
    monkeypatch.setattr(
        _gh, "run_gh",
        _recording_run_gh(calls, ["atdd-issue", "atdd:RED"]),
    )

    issue_state.transition_phase(ISSUE, "COMPLETE")

    removed = [c[-1] for c in calls if "--remove-label" in c]
    assert removed == ["atdd:RED"], (
        f"only the stale phase label may be removed, got {removed}"
    )


def test_transition_phase_skips_redundant_remove(monkeypatch):
    """Re-applying the same phase does not remove-then-add the live label."""
    calls = []
    monkeypatch.setattr(
        _gh, "run_gh",
        _recording_run_gh(calls, ["atdd-issue", "atdd:GREEN"]),
    )

    issue_state.transition_phase(ISSUE, "GREEN")

    assert ["issue", "edit", str(ISSUE), "--remove-label", "atdd:GREEN"] not in calls
