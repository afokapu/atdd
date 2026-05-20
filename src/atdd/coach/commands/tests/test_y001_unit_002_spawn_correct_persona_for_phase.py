# URN: test:drive-state-machine:coach-state-machine-and-runtime:Y001-UNIT-002-spawn-correct-persona-for-phase
# Acceptance: acc:drive-state-machine:Y001-UNIT-002-spawn-correct-persona-for-phase
# WMBT: wmbt:drive-state-machine:Y001
# Phase: RED
# Layer: application
"""Y001-UNIT-002 — warm-resume spawns tester not planner when issue is at PLANNED.

Issue #712 Edge A. The current code always spawns the planner as its first
spawn call (Transition(INIT, PLANNED)) regardless of the issue's actual
phase. For a PLANNED issue, the first spawn must be the tester
(Transition(PLANNED, RED)) with no planner spawn at all.

RED until _drive_single_issue reads the GitHub phase and routes accordingly.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def _make_cfg(tmp_path=None, *, issue_numbers=(690,), dry_run: bool = False):
    from atdd.coach.commands.coach import Config
    return Config(
        issue_numbers=list(issue_numbers),
        dry_run=dry_run,
        skip_review=True,
    )


def test_warm_resume_planned_does_not_spawn_planner(tmp_path, monkeypatch):
    """_drive_single_issue on a PLANNED issue must not call spawn with INIT→PLANNED."""
    from atdd.coach.commands.coach import Phase, _drive_single_issue, _read_current_github_phase
    from atdd.coach.handlers.state_machine import HandlerResult, StateMachine

    # Stub GitHub label read to report PLANNED
    monkeypatch.setattr(
        "atdd.coach.commands.coach._read_current_github_phase",
        lambda _issue: Phase.PLANNED,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.coach._swap_phase_label",
        lambda _issue, _phase: None,
    )

    spawn_calls: list = []

    def stub_spawn(ctx, transition):
        spawn_calls.append((transition.src, transition.dst))
        return HandlerResult.HANDLED

    cfg = _make_cfg(tmp_path, dry_run=True)
    sm = StateMachine(issue_number=690, phase=Phase.INIT)

    _drive_single_issue(
        cfg, sm, tmp_path,
        _spawn_func=stub_spawn,
        _max_loop_events=0,
    )

    planner_calls = [(s, d) for s, d in spawn_calls if s == Phase.INIT and d == Phase.PLANNED]
    assert len(planner_calls) == 0, (
        f"Expected no planner spawn for PLANNED issue; got spawn_calls={spawn_calls}"
    )


def test_warm_resume_planned_first_spawn_is_tester(tmp_path, monkeypatch):
    """The first spawn call for a PLANNED issue must be Transition(PLANNED, RED)."""
    from atdd.coach.commands.coach import Phase, _drive_single_issue
    from atdd.coach.handlers.state_machine import HandlerResult, StateMachine

    monkeypatch.setattr(
        "atdd.coach.commands.coach._read_current_github_phase",
        lambda _issue: Phase.PLANNED,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.coach._swap_phase_label",
        lambda _issue, _phase: None,
    )

    spawn_calls: list = []

    def stub_spawn(ctx, transition):
        spawn_calls.append((transition.src, transition.dst))
        return HandlerResult.HANDLED

    cfg = _make_cfg(tmp_path, dry_run=True)
    sm = StateMachine(issue_number=690, phase=Phase.INIT)

    _drive_single_issue(
        cfg, sm, tmp_path,
        _spawn_func=stub_spawn,
        _max_loop_events=0,
    )

    assert len(spawn_calls) >= 1, "Expected at least one spawn call"
    first_src, first_dst = spawn_calls[0]
    assert first_src == Phase.PLANNED and first_dst == Phase.RED, (
        f"Expected first spawn Transition(PLANNED, RED); got ({first_src}, {first_dst}). "
        f"All calls: {spawn_calls}"
    )
