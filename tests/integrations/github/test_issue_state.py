"""Fixture-based tests for ``atdd.integrations.github.issue_state`` (no live API).

Covers the #882 fix: ``transition_phase`` swaps the label AND syncs the board
through a single owner so they cannot drift.
"""
from __future__ import annotations

import json
import logging

import pytest

from atdd.integrations.github import _gh, issue_state, projects_v2

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


def test_transition_phase_swaps_label_and_syncs_board(monkeypatch):
    """The #882 guarantee: one call swaps the label AND syncs Projects v2."""
    calls = []
    monkeypatch.setattr(
        _gh, "run_gh",
        _recording_run_gh(calls, ["atdd-issue", "atdd:RED"]),
    )
    synced = []
    monkeypatch.setattr(
        projects_v2, "sync_status_field",
        lambda issue, phase, **kw: synced.append((issue, phase)),
    )

    issue_state.transition_phase(ISSUE, "COMPLETE")

    edit_calls = [c for c in calls if c[:2] == ["issue", "edit"]]
    assert ["issue", "edit", str(ISSUE), "--remove-label", "atdd:RED"] in edit_calls
    assert ["issue", "edit", str(ISSUE), "--add-label", "atdd:COMPLETE"] in edit_calls
    # Atomic board sync happened in the same call → label & board never drift.
    assert synced == [(ISSUE, "COMPLETE")]


def test_transition_phase_degrades_to_label_only_without_token(
    monkeypatch, caplog
):
    """No PROJECT_TOKEN → label still swaps, board sync skipped with a warning."""
    monkeypatch.delenv(_gh.PROJECT_TOKEN_ENV, raising=False)
    calls = []
    monkeypatch.setattr(
        _gh, "run_gh",
        _recording_run_gh(calls, ["atdd-issue", "atdd:SMOKE"]),
    )

    with caplog.at_level(logging.WARNING):
        issue_state.transition_phase(ISSUE, "REFACTOR")  # must not raise

    assert ["issue", "edit", str(ISSUE), "--add-label", "atdd:REFACTOR"] in calls
    assert any("PROJECT_TOKEN" in r.getMessage() for r in caplog.records)


def test_transition_phase_skips_redundant_remove(monkeypatch):
    """Re-applying the same phase does not remove-then-add the live label."""
    calls = []
    monkeypatch.setattr(
        _gh, "run_gh",
        _recording_run_gh(calls, ["atdd-issue", "atdd:GREEN"]),
    )
    monkeypatch.setattr(projects_v2, "sync_status_field", lambda *a, **k: None)

    issue_state.transition_phase(ISSUE, "GREEN")

    assert ["issue", "edit", str(ISSUE), "--remove-label", "atdd:GREEN"] not in calls
