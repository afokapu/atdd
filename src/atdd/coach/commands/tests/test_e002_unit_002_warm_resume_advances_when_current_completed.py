# URN: test:drive-state-machine:phase-advance-requires-completion-match:E002-UNIT-002-warm-resume-advances-when-current-completed
# Acceptance: acc:drive-state-machine:E002-UNIT-002-warm-resume-advances-when-current-completed
# WMBT: wmbt:drive-state-machine:E002
# Phase: RED
# Harness: unit
# Layer: application
"""E002-UNIT-002 — warm-resume advances current→next ONLY when the current phase completed.

Issue #1055. Companion to E002-UNIT-001. The completion gate is a phase-tagged
``done.json`` marker for the CURRENT phase (the tester persona writes
``atdd agent done --summary "RED: …"`` — the planner cites this summary phase-
prefix as the marker). When that marker is present, warm-resume advances RED→GREEN
and spawns the GREEN persona; when it is absent it must NOT advance.

This test pins the "only when present" half of the gate by driving BOTH scenarios:
  * marker present  → advances to GREEN, spawns Transition(RED, GREEN), label→GREEN once
  * marker absent   → stays at RED (does NOT advance)

RED until the gate is implemented: on current code warm-resume advances
unconditionally, so the marker-absent scenario wrongly advances to GREEN and this
test fails.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _make_cfg(*, issue_numbers=(1051,), dry_run: bool = True):
    from atdd.coach.commands.coach import Config
    return Config(
        issue_numbers=list(issue_numbers),
        dry_run=dry_run,
        skip_review=True,
    )


def _write_red_marker(runtime_dir: Path, issue: int) -> None:
    """Write a phase-tagged completion marker for the RED phase.

    Mirrors the existing done.json convention (runtime/agents/<agent_id>/done.json)
    with a phase-prefixed summary — the same shape the RED tester emits via
    ``atdd agent done --summary "RED: …"``.
    """
    agent_dir = runtime_dir / "agents" / f"tester-{issue}-deadbeef"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "done.json").write_text(
        json.dumps({"timestamp": "2026-06-11T00:00:00Z",
                    "summary": "RED: 4 failing tests written for 4 acceptances"}),
        encoding="utf-8",
    )


def _drive_warm_resume_at_red(tmp_path, monkeypatch, *, with_marker: bool):
    from atdd.coach.commands.coach import Phase
    from atdd.coach.handlers.state_machine import HandlerResult, StateMachine
    from atdd.train.issue_runner import drive_single_issue

    monkeypatch.setattr(
        "atdd.coach.commands.coach._read_current_github_phase",
        lambda _issue: Phase.RED,
    )
    label_swaps: list = []
    monkeypatch.setattr(
        "atdd.coach.commands.coach._swap_phase_label",
        lambda _issue, phase: label_swaps.append(phase),
    )

    if with_marker:
        _write_red_marker(tmp_path, 1051)

    spawn_calls: list = []

    def stub_spawn(ctx, transition):
        spawn_calls.append((transition.src, transition.dst))
        return HandlerResult.HANDLED

    cfg = _make_cfg()
    sm = StateMachine(issue_number=1051, phase=Phase.INIT)
    rc = drive_single_issue(
        cfg, sm, tmp_path,
        _spawn_func=stub_spawn,
        _max_loop_events=0,
    )
    return rc, sm, spawn_calls, label_swaps


def test_warm_resume_with_red_marker_advances_to_green(tmp_path, monkeypatch):
    """Marker present → advance RED→GREEN and spawn the GREEN persona once."""
    from atdd.coach.commands.coach import Phase

    runtime = tmp_path / "with_marker"
    rc, sm, spawn_calls, label_swaps = _drive_warm_resume_at_red(
        runtime, monkeypatch, with_marker=True,
    )

    assert rc == 0, f"Expected rc=0; got {rc}"
    assert spawn_calls == [(Phase.RED, Phase.GREEN)], (
        f"With a RED completion marker, warm-resume must spawn Transition(RED,GREEN); "
        f"got {spawn_calls}"
    )
    assert sm.phase == Phase.GREEN, f"Expected sm.phase=GREEN; got {sm.phase}"
    assert label_swaps == [Phase.GREEN], (
        f"Label must be swapped to GREEN exactly once; got {label_swaps}"
    )


def test_warm_resume_without_red_marker_does_not_advance(tmp_path, monkeypatch):
    """Marker absent → must NOT advance (the 'only when present' half of the gate).

    This is the assertion current code violates: it advances unconditionally.
    """
    from atdd.coach.commands.coach import Phase

    runtime = tmp_path / "no_marker"
    rc, sm, spawn_calls, label_swaps = _drive_warm_resume_at_red(
        runtime, monkeypatch, with_marker=False,
    )

    assert rc == 0, f"Expected rc=0; got {rc}"
    assert sm.phase != Phase.GREEN, (
        f"Without a RED completion marker, warm-resume must NOT advance to GREEN; "
        f"got sm.phase={sm.phase}, spawn_calls={spawn_calls}"
    )
    assert Phase.GREEN not in label_swaps, (
        f"Label must not be swapped to GREEN without a marker; got {label_swaps}"
    )
