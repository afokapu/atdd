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

import pytest

pytestmark = [pytest.mark.platform]


def _make_cfg(tmp_path=None, *, issue_numbers=(690,), dry_run: bool = False):
    from atdd.coach.commands.coach import Config
    return Config(
        issue_numbers=list(issue_numbers),
        dry_run=dry_run,
        skip_review=True,
    )


def test_warm_resume_from_green_reaches_smoke_without_events(tmp_path, monkeypatch):
    """_drive_single_issue on a GREEN issue: warm-resume spawns (GREEN,SMOKE) and advances SM to SMOKE.

    With the new warm-resume design, spawn+advance mirrors cold-start's INIT→PLANNED:
    the warm-resume spawns the tester for SMOKE and immediately advances SM to SMOKE.
    No events are needed — the SM is at SMOKE before the event loop even starts.
    This is the fix for Edge C: the loop guard sees SMOKE (not GREEN) so it correctly
    continues waiting for the SMOKE tester to write done.json.
    """
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

    cfg = _make_cfg(tmp_path, dry_run=True)
    sm = StateMachine(issue_number=690, phase=Phase.INIT)

    rc = _drive_single_issue(
        cfg, sm, tmp_path,
        _spawn_func=stub_spawn,
        _max_loop_events=0,  # no events; warm-resume advance is the only state change
    )

    assert rc == 0, f"Expected rc=0; got {rc}"
    assert sm.phase == Phase.SMOKE, (
        f"Expected sm.phase=SMOKE after warm-resume at GREEN; got {sm.phase}. "
        f"spawn_calls={spawn_calls}"
    )
    assert Phase.BLOCKED not in sm.history, (
        f"SM must not enter BLOCKED; history={sm.history}"
    )
    # The warm-resume must have spawned the tester for GREEN→SMOKE
    assert spawn_calls == [(Phase.GREEN, Phase.SMOKE)], (
        f"Expected exactly one warm-resume spawn (GREEN,SMOKE); got {spawn_calls}"
    )
