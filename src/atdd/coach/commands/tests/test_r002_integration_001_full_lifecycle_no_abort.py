# URN: test:drive-state-machine:coach-state-machine-and-runtime:R002-INTEGRATION-001-full-lifecycle-no-abort
# Acceptance: acc:drive-state-machine:R002-INTEGRATION-001-full-lifecycle-no-abort
# WMBT: wmbt:drive-state-machine:R002
# Phase: RED
# Layer: integration
"""R002-INTEGRATION-001 — full PLANNED→RED→GREEN→SMOKE→REFACTOR drive without abort.

Issue #712 Edge C + Edge A together. _drive_single_issue on a PLANNED issue
with four injected agent_done events drives through the complete lifecycle to
REFACTOR without entering BLOCKED.

RED until Edge A (warm-resume) and Edge B (label sync) are implemented; this
test monkeypatches _read_current_github_phase and _swap_phase_label but
those symbols don't yet exist, causing ImportError.
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


def test_full_lifecycle_from_planned_to_refactor(tmp_path, monkeypatch):
    """PLANNED issue: four injected events drive to REFACTOR; SM never BLOCKED."""
    from atdd.coach.commands.coach import Phase, _drive_single_issue
    from atdd.coach.handlers.state_machine import HandlerResult, StateMachine

    # #1055 — warm-resume advances only when the CURRENT (PLANNED) phase completed.
    _write_phase_marker(tmp_path, 690, "planner", "PLANNED")

    monkeypatch.setattr(
        "atdd.coach.commands.coach._read_current_github_phase",
        lambda _issue: Phase.PLANNED,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.coach._swap_phase_label",
        lambda _issue, _phase: None,
    )

    spawn_calls: list = []

    def stub_spawn(ctx, t):
        spawn_calls.append((t.src, t.dst))
        return HandlerResult.HANDLED

    # Warm-resume at PLANNED: spawns tester (PLANNED→RED) and advances SM to RED.
    # Then 3 events drive RED→GREEN→SMOKE→REFACTOR. #1055: each agent_done must
    # carry the COMPLETING phase (done.json summary phase-prefix) matching sm.phase
    # at that step — the persona-phase gate ignores a done whose phase != sm.phase.
    events = [
        {"event_type": "agent_done", "agent_id": "tester-690-bbb",
         "payload": {"summary": "RED: tests written"}},      # RED→GREEN
        {"event_type": "agent_done", "agent_id": "coder-690-ccc",
         "payload": {"summary": "GREEN: impl done"}},        # GREEN→SMOKE
        {"event_type": "agent_done", "agent_id": "tester-690-ddd",
         "payload": {"summary": "SMOKE: smoke verified"}},   # SMOKE→REFACTOR
    ]

    cfg = _make_cfg(tmp_path, dry_run=True)
    sm = StateMachine(issue_number=690, phase=Phase.INIT)

    rc = _drive_single_issue(
        cfg, sm, tmp_path,
        _spawn_func=stub_spawn,
        _injected_events=events,
    )

    assert rc == 0, f"Expected rc=0; got {rc}"
    assert sm.phase == Phase.REFACTOR, (
        f"Expected sm.phase=REFACTOR after warm-resume + 3 advances; got {sm.phase}. "
        f"history={sm.history}, spawn_calls={spawn_calls}"
    )
    assert Phase.BLOCKED not in sm.history, (
        f"SM must never enter BLOCKED; history={sm.history}"
    )

    # Warm-resume spawns (PLANNED, RED); then event loop spawns (RED,GREEN), (GREEN,SMOKE), (SMOKE,REFACTOR)
    expected_transitions = [
        (Phase.PLANNED, Phase.RED),
        (Phase.RED, Phase.GREEN),
        (Phase.GREEN, Phase.SMOKE),
        (Phase.SMOKE, Phase.REFACTOR),
    ]
    assert spawn_calls == expected_transitions, (
        f"Expected spawn transitions {expected_transitions}; got {spawn_calls}"
    )
