# URN: test:drive-state-machine:coach-state-machine-and-runtime:Y002-UNIT-002-label-swapped-on-each-watcher-advance
# Acceptance: acc:drive-state-machine:Y002-UNIT-002-label-swapped-on-each-watcher-advance
# WMBT: wmbt:drive-state-machine:Y002
# Phase: RED
# Layer: application
"""Y002-UNIT-002 — _swap_phase_label called after each SM advance in injected event path.

Issue #712 Edge B. The current code advances sm.phase and writes a decision
but never calls any label-swap function. This test starts at PLANNED (warm-resume)
and injects two events (RED→GREEN, GREEN→SMOKE). Three _swap_phase_label calls must
occur: one for the warm-resume advance (PLANNED→RED) plus one per injected event.

RED until _swap_phase_label is wired into the advance path.
"""
from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.platform]


def _make_cfg(tmp_path=None, *, issue_numbers=(690,), dry_run: bool = False):
    from atdd.coach.commands.coach import Config
    return Config(
        issue_numbers=list(issue_numbers),
        dry_run=dry_run,
        skip_review=True,
    )


def _write_phase_marker(runtime_dir, issue, persona, phase_name):
    """Write a phase-tagged done.json — the completion marker warm-resume gates on (#1055)."""
    agent_dir = runtime_dir / "agents" / f"{persona}-{issue}-deadbeef"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "done.json").write_text(
        json.dumps({"timestamp": "2026-06-11T00:00:00Z", "summary": f"{phase_name}: done"}),
        encoding="utf-8",
    )


def test_two_injected_advances_call_swap_phase_label_twice(tmp_path, monkeypatch):
    """Warm-resume at PLANNED + 2 events trigger three _swap_phase_label calls.

    Call sequence: RED (warm-resume PLANNED→RED), GREEN (event1 RED→GREEN),
    SMOKE (event2 GREEN→SMOKE). Every advance — including the warm-resume
    advance — must produce exactly one label swap.
    """
    from atdd.coach.commands.coach import Phase, _drive_single_issue
    from atdd.coach.handlers.state_machine import HandlerResult, StateMachine

    swap_calls: list = []

    # #1055 — warm-resume advances only when the CURRENT (PLANNED) phase completed.
    _write_phase_marker(tmp_path, 690, "planner", "PLANNED")

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
        {"event_type": "agent_done", "agent_id": "tester-690-aaa"},   # RED→GREEN
        {"event_type": "agent_done", "agent_id": "coder-690-bbb"},    # GREEN→SMOKE
    ]

    cfg = _make_cfg(tmp_path, dry_run=True)
    sm = StateMachine(issue_number=690, phase=Phase.INIT)

    _drive_single_issue(
        cfg, sm, tmp_path,
        _spawn_func=stub_spawn,
        _injected_events=events,
    )

    assert len(swap_calls) == 3, (
        f"Expected 3 _swap_phase_label calls (warm-resume + 2 events); got {len(swap_calls)}: {swap_calls}"
    )
    assert swap_calls[0] == Phase.RED, (
        f"First swap (warm-resume) should be Phase.RED; got {swap_calls[0]}"
    )
    assert swap_calls[1] == Phase.GREEN, (
        f"Second swap (event1) should be Phase.GREEN; got {swap_calls[1]}"
    )
    assert swap_calls[2] == Phase.SMOKE, (
        f"Third swap (event2) should be Phase.SMOKE; got {swap_calls[2]}"
    )
