# URN: test:integration-hardening:two-phase-commit-wiring:P001-INTEGRATION-001-complete-triggers-merge
# Acceptance: acc:integration-hardening:P001-INTEGRATION-001-complete-triggers-merge
# WMBT: wmbt:integration-hardening:P001
# Phase: RED
# Layer: integration
"""P001-INTEGRATION-001 — with --auto-merge, COMPLETE → MERGED triggers PR creation + merge.

Verifies that the two-phase commit handler:
  1. Invokes `atdd pr <N>` (Phase A — validates default-branch base per #477)
  2. Invokes `gh pr merge --squash --delete-branch` (Phase B)
  3. `atdd pr` precedes `gh pr merge` (ordering invariant)
  4. Returns HandlerResult.HANDLED on success
  5. Returns HandlerResult.ERROR when PR creation fails
  6. Returns HandlerResult.ERROR when merge fails

Review note (2026-05-11 afokapu): Phase C (release tagging) omitted —
publish.yml owns tagging on push-to-main. Cleanup fail → MERGED with
warning (not ERROR). CI fail → check mergeStateStatus, surface on
escalation channel.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.platform]


def _make_ctx(issue_number: int = 590, *, auto_merge: bool = True, escalation_channel=None):
    from atdd.coach.handlers.state_machine import CoachContext
    return CoachContext(
        issue_number=issue_number,
        auto_merge=auto_merge,
        escalation_channel=escalation_channel,
    )


def _make_transition(src="COMPLETE", dst="MERGED"):
    from atdd.coach.handlers.state_machine import Phase, Transition
    return Transition(src=Phase(src), dst=Phase(dst))


def _fake_subprocess(returncode: int = 0, stdout: str = "", stderr: str = ""):
    """Return a mock subprocess module where .run() always succeeds."""
    result = SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
    mod = MagicMock()
    mod.run.return_value = result
    return mod


class _CallTracker:
    """Records every subprocess.run call and lets per-cmd returncode be set."""

    def __init__(self, overrides: dict[str, int] | None = None):
        self.calls: list[list[str]] = []
        self._overrides = overrides or {}

    def run(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        key = " ".join(cmd)
        rc = next(
            (v for k, v in self._overrides.items() if k in key),
            0,
        )
        return SimpleNamespace(returncode=rc, stdout="", stderr=f"mock error for {key}" if rc != 0 else "")

    def cmd_strs(self) -> list[str]:
        return [" ".join(c) for c in self.calls]


def test_auto_merge_invokes_atdd_pr_then_gh_merge(monkeypatch):
    """P001-INTEGRATION-001: handler calls atdd pr <N> then gh pr merge, in that order."""
    import atdd.coach.handlers.two_phase_commit as tpc
    from atdd.coach.handlers.state_machine import HandlerResult

    tracker = _CallTracker()
    monkeypatch.setattr(tpc, "subprocess", tracker)

    result = tpc.handle(_make_ctx(590, auto_merge=True), _make_transition())

    assert result == HandlerResult.HANDLED
    cmds = tracker.cmd_strs()
    pr_indices = [i for i, s in enumerate(cmds) if "atdd" in s and "pr" in s and "590" in s]
    merge_indices = [i for i, s in enumerate(cmds) if "gh" in s and "merge" in s]
    squash_indices = [i for i, s in enumerate(cmds) if "--squash" in s]
    delete_indices = [i for i, s in enumerate(cmds) if "--delete-branch" in s]

    assert pr_indices, f"Expected atdd pr 590 in calls: {cmds}"
    assert merge_indices, f"Expected gh pr merge in calls: {cmds}"
    assert squash_indices, f"Expected --squash in calls: {cmds}"
    assert delete_indices, f"Expected --delete-branch in calls: {cmds}"
    assert pr_indices[0] < merge_indices[0], "atdd pr must precede gh pr merge"


def test_auto_merge_returns_error_on_pr_creation_failure(monkeypatch):
    """P001-INTEGRATION-001: if atdd pr fails, handler returns ERROR and skips merge."""
    import atdd.coach.handlers.two_phase_commit as tpc
    from atdd.coach.handlers.state_machine import HandlerResult

    tracker = _CallTracker(overrides={"atdd pr": 1})
    monkeypatch.setattr(tpc, "subprocess", tracker)

    result = tpc.handle(_make_ctx(auto_merge=True), _make_transition())

    assert result == HandlerResult.ERROR
    merge_calls = [c for c in tracker.cmd_strs() if "gh" in c and "merge" in c]
    assert not merge_calls, "gh pr merge must not be called when atdd pr fails"


def test_auto_merge_returns_error_on_merge_failure(monkeypatch):
    """P001-INTEGRATION-001: if gh pr merge fails, handler returns ERROR."""
    import atdd.coach.handlers.two_phase_commit as tpc
    from atdd.coach.handlers.state_machine import HandlerResult

    tracker = _CallTracker(overrides={"gh pr merge": 1})
    monkeypatch.setattr(tpc, "subprocess", tracker)

    result = tpc.handle(_make_ctx(auto_merge=True), _make_transition())

    assert result == HandlerResult.ERROR


def test_non_complete_to_merged_transition_is_noop(monkeypatch):
    """P2: handler is a no-op for transitions other than COMPLETE → MERGED."""
    import atdd.coach.handlers.two_phase_commit as tpc
    from atdd.coach.handlers.state_machine import HandlerResult

    tracker = _CallTracker()
    monkeypatch.setattr(tpc, "subprocess", tracker)

    result = tpc.handle(_make_ctx(auto_merge=True), _make_transition("REFACTOR", "COMPLETE"))

    assert result == HandlerResult.NOOP
    assert tracker.calls == [], "No subprocess calls for non-COMPLETE→MERGED transitions"


def test_complete_to_merged_noop_for_other_dst(monkeypatch):
    """P2: only COMPLETE → MERGED is handled; other dst from COMPLETE is noop."""
    import atdd.coach.handlers.two_phase_commit as tpc
    from atdd.coach.handlers.state_machine import HandlerResult

    tracker = _CallTracker()
    monkeypatch.setattr(tpc, "subprocess", tracker)

    # COMPLETE can only legally go to MERGED per the state machine, but the
    # handler itself must be defensive about the transition.
    result = tpc.handle(_make_ctx(auto_merge=True), _make_transition("BLOCKED", "INIT"))

    assert result == HandlerResult.NOOP
    assert tracker.calls == []
