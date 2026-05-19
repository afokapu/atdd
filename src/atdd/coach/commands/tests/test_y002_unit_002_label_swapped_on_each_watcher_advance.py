# URN: test:drive-state-machine:coach-state-machine-and-runtime:Y002-UNIT-002-label-swapped-on-each-watcher-advance
# Acceptance: acc:drive-state-machine:Y002-UNIT-002-label-swapped-on-each-watcher-advance
# WMBT: wmbt:drive-state-machine:Y002
# Phase: RED
# Layer: application
"""Y002-UNIT-002 — _swap_phase_label called after each SM advance in injected event path.

Issue #712 Edge B. The current code advances sm.phase and writes a decision
but never calls any label-swap function. This test injects two events
(PLANNED→RED, RED→GREEN) and verifies _swap_phase_label is called once per
advance with the new phase.

RED until _swap_phase_label is wired into the advance path.
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


def test_two_injected_advances_call_swap_phase_label_twice(tmp_path, monkeypatch):
    """Two injected events (PLANNED→RED, RED→GREEN) trigger two _swap_phase_label calls."""
    from atdd.coach.commands.coach import (
        Phase, _drive_single_issue, _read_current_github_phase,
    )
    from atdd.coach.handlers.state_machine import HandlerResult, StateMachine

    swap_calls: list = []

    # Stub warm-resume to return PLANNED
    monkeypatch.setattr(
        "atdd.coach.commands.coach._read_current_github_phase",
        lambda _issue: Phase.PLANNED,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.coach._swap_phase_label",
        lambda issue, phase: swap_calls.append(phase),
    )

    def stub_spawn(ctx, t):
        return HandlerResult.HANDLED

    events = [
        {"event_type": "agent_done", "agent_id": "tester-690-aaa"},   # PLANNED→RED
        {"event_type": "agent_done", "agent_id": "coder-690-bbb"},    # RED→GREEN
    ]

    cfg = _make_cfg(tmp_path, dry_run=True)
    sm = StateMachine(issue_number=690, phase=Phase.INIT)

    _drive_single_issue(
        cfg, sm, tmp_path,
        _spawn_func=stub_spawn,
        _injected_events=events,
    )

    assert len(swap_calls) == 2, (
        f"Expected 2 _swap_phase_label calls (one per advance); got {len(swap_calls)}: {swap_calls}"
    )
    assert swap_calls[0] == Phase.RED, (
        f"First swap should be Phase.RED; got {swap_calls[0]}"
    )
    assert swap_calls[1] == Phase.GREEN, (
        f"Second swap should be Phase.GREEN; got {swap_calls[1]}"
    )
