# URN: test:drive-state-machine:coach-state-machine-and-runtime:Y001-INTEGRATION-001-warm-resume-skips-planner
# Acceptance: acc:drive-state-machine:Y001-INTEGRATION-001-warm-resume-skips-planner
# WMBT: wmbt:drive-state-machine:Y001
# Phase: RED
# Layer: integration
"""Y001-INTEGRATION-001 — full _drive_single_issue warm-resume: tester spawned, not planner.

Issue #712 Edge A. Full call to _drive_single_issue on a PLANNED issue via
injected events. The SM history must not contain a INIT→PLANNED transition;
spawn must be called with Transition(PLANNED, RED) exactly once on entry.

RED until warm-resume dispatch is implemented.
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


def test_integration_warm_resume_on_planned_issue(tmp_path, monkeypatch):
    """_drive_single_issue on a PLANNED issue: spawns Transition(PLANNED,RED), advances SM to RED."""
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

    rc = _drive_single_issue(
        cfg, sm, tmp_path,
        _spawn_func=stub_spawn,
        _max_loop_events=0,
    )

    assert rc == 0, f"Expected return code 0, got {rc}"

    # Must have called spawn with PLANNED→RED exactly once (warm-resume dispatch)
    planned_to_red = [(s, d) for s, d in spawn_calls if s == Phase.PLANNED and d == Phase.RED]
    assert len(planned_to_red) == 1, (
        f"Expected exactly one Transition(PLANNED,RED) spawn; got {spawn_calls}"
    )

    # Must NOT have called spawn with INIT→PLANNED (cold-start path skipped)
    init_calls = [(s, d) for s, d in spawn_calls if s == Phase.INIT]
    assert len(init_calls) == 0, (
        f"Warm resume must not spawn planner; INIT spawn calls: {init_calls}"
    )

    # SM must be at RED after warm-resume advance (spawn + advance mirrors cold-start INIT→PLANNED)
    assert sm.phase == Phase.RED, (
        f"Expected sm.phase=RED after warm-resume spawn+advance; got {sm.phase}"
    )
