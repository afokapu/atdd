# URN: test:integration-hardening:two-phase-commit-wiring:P001-INTEGRATION-003-no-auto-merge-without-flag
# Acceptance: acc:integration-hardening:P001-INTEGRATION-003-no-auto-merge-without-flag
# WMBT: wmbt:integration-hardening:P001
# Phase: RED
# Layer: integration
"""P001-INTEGRATION-003 — without --auto-merge, COMPLETE stays pending + escalation sent.

Verifies that:
  1. With auto_merge=False, handler returns HandlerResult.NOOP (COMPLETE
     remains pending operator approval).
  2. No `atdd pr` or `gh pr merge` subprocess calls are made.
  3. An escalation message is printed to stderr.
  4. When escalation_channel is set, the channel name appears in the output.
  5. Operator can resume via `atdd coach <N> --auto-merge` (the escalation
     message must contain the manual-resume hint).
"""
from __future__ import annotations

import io
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.platform]


def _make_ctx(issue_number: int = 590, *, auto_merge: bool = False, escalation_channel=None):
    from atdd.coach.handlers.state_machine import CoachContext
    return CoachContext(
        issue_number=issue_number,
        auto_merge=auto_merge,
        escalation_channel=escalation_channel,
    )


def _make_transition():
    from atdd.coach.handlers.state_machine import Phase, Transition
    return Transition(src=Phase.COMPLETE, dst=Phase.MERGED)


def test_no_auto_merge_returns_noop(monkeypatch):
    """P001-INTEGRATION-003: auto_merge=False → NOOP (COMPLETE stays pending)."""
    import atdd.coach.handlers.two_phase_commit as tpc
    from atdd.coach.handlers.state_machine import HandlerResult

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    mod = MagicMock()
    mod.run.side_effect = fake_run
    monkeypatch.setattr(tpc, "subprocess", mod)

    result = tpc.handle(_make_ctx(auto_merge=False), _make_transition())

    assert result == HandlerResult.NOOP


def test_no_auto_merge_makes_no_pr_or_merge_calls(monkeypatch):
    """P001-INTEGRATION-003: no `atdd pr` or `gh pr merge` calls when auto_merge=False."""
    import atdd.coach.handlers.two_phase_commit as tpc

    recorded: list[list[str]] = []

    mod = MagicMock()
    mod.run.side_effect = lambda cmd, **kw: (
        recorded.append(list(cmd)) or SimpleNamespace(returncode=0, stdout="", stderr="")
    )
    monkeypatch.setattr(tpc, "subprocess", mod)

    tpc.handle(_make_ctx(auto_merge=False), _make_transition())

    pr_calls = [c for c in recorded if "atdd" in c and "pr" in c]
    merge_calls = [c for c in recorded if "gh" in c and "merge" in c]
    assert not pr_calls, f"Unexpected atdd pr call when auto_merge=False: {pr_calls}"
    assert not merge_calls, f"Unexpected gh pr merge call when auto_merge=False: {merge_calls}"


def test_no_auto_merge_sends_escalation_to_stderr(monkeypatch, capsys):
    """P001-INTEGRATION-003: escalation message printed to stderr."""
    import atdd.coach.handlers.two_phase_commit as tpc

    mod = MagicMock()
    mod.run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(tpc, "subprocess", mod)

    tpc.handle(_make_ctx(590, auto_merge=False), _make_transition())

    captured = capsys.readouterr()
    assert "590" in captured.err, f"Issue number not in escalation output: {captured.err!r}"
    assert "COMPLETE" in captured.err or "auto-merge" in captured.err, (
        f"Escalation hint not in stderr: {captured.err!r}"
    )


def test_no_auto_merge_escalation_includes_channel(monkeypatch, capsys):
    """P001-INTEGRATION-003: when escalation_channel is set, it appears in stderr."""
    import atdd.coach.handlers.two_phase_commit as tpc

    mod = MagicMock()
    mod.run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(tpc, "subprocess", mod)

    tpc.handle(
        _make_ctx(590, auto_merge=False, escalation_channel="slack:#coach-alerts"),
        _make_transition(),
    )

    captured = capsys.readouterr()
    assert "slack:#coach-alerts" in captured.err, (
        f"escalation_channel not in stderr: {captured.err!r}"
    )


def test_no_auto_merge_escalation_includes_manual_resume_hint(monkeypatch, capsys):
    """P001-INTEGRATION-003: escalation message tells operator how to complete the merge."""
    import atdd.coach.handlers.two_phase_commit as tpc

    mod = MagicMock()
    mod.run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(tpc, "subprocess", mod)

    tpc.handle(_make_ctx(590, auto_merge=False), _make_transition())

    captured = capsys.readouterr()
    assert "--auto-merge" in captured.err, (
        f"Manual resume hint (--auto-merge) missing from escalation: {captured.err!r}"
    )
