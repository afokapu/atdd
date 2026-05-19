# URN: test:drive-state-machine:coach-state-machine-and-runtime:R002-UNIT-002-loop-continues-through-green
# Acceptance: acc:drive-state-machine:R002-UNIT-002-loop-continues-through-green
# WMBT: wmbt:drive-state-machine:R002
# Phase: RED
# Layer: application
"""R002-UNIT-002 — _process_injected_events continues from GREEN to SMOKE without BLOCKED.

Issue #712 Edge C. When _drive_single_issue is called on a GREEN issue via
warm-resume and one agent_done event is injected for the GREEN coder, the
SM must advance to SMOKE (not RED, not BLOCKED).

With the current cold-start-always code, this FAILS: _drive_single_issue
writes INIT→PLANNED and sets sm.phase=PLANNED before the event loop. The
agent_done event then maps to PLANNED→RED, not GREEN→SMOKE.

RED until Edge A (warm-resume) is fixed so the SM starts at GREEN.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _make_cfg(tmp_path: Path, *, dry_run: bool = False):
    from atdd.coach.commands.coach import Config
    return Config(
        issue_numbers=[690],
        dry_run=dry_run,
        llm="claude-code",
        worktree_root=str(tmp_path),
        no_progress_ttl=None,
        escalation_channel=None,
        skip_review=True,
        risk_threshold_block=None,
        allow_stale_suppressions=False,
        auto_merge=False,
        max_retries=0,
        multiplexer_backend="tmux",
        worktree_override=str(tmp_path / "worktree"),
    )


def test_warm_resume_from_green_advances_to_smoke(tmp_path, monkeypatch):
    """_drive_single_issue on a GREEN issue with one injected event reaches SMOKE, not RED."""
    from atdd.coach.commands.coach import Phase, _drive_single_issue
    from atdd.coach.handlers.state_machine import HandlerResult, StateMachine

    monkeypatch.setattr(
        "atdd.coach.commands.coach._read_current_github_phase",
        lambda _issue: Phase.GREEN,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.coach._swap_phase_label",
        lambda _issue, _phase: None,
    )

    spawn_calls: list = []

    def stub_spawn(ctx, t):
        spawn_calls.append((t.src, t.dst))
        return HandlerResult.HANDLED

    # One agent_done from the GREEN coder persona
    events = [
        {"event_type": "agent_done", "agent_id": "coder-690-abc"},
    ]

    cfg = _make_cfg(tmp_path, dry_run=True)
    sm = StateMachine(issue_number=690, phase=Phase.INIT)

    rc = _drive_single_issue(
        cfg, sm, tmp_path,
        _spawn_func=stub_spawn,
        _injected_events=events,
    )

    assert rc == 0, f"Expected rc=0; got {rc}"
    assert sm.phase == Phase.SMOKE, (
        f"Expected sm.phase=SMOKE after GREEN coder done; got {sm.phase}. "
        f"spawn_calls={spawn_calls}"
    )
    assert Phase.BLOCKED not in sm.history, (
        f"SM must not enter BLOCKED; history={sm.history}"
    )
