# URN: test:drive-state-machine:coach-state-machine-and-runtime:D001-UNIT-001-state-machine-skeleton
# Acceptance: acc:drive-state-machine:D001-UNIT-001-state-machine-skeleton
# WMBT: wmbt:drive-state-machine:D001
# Phase: RED
# Layer: application
"""D001-UNIT-001 — `atdd coach <issue>` initializes a state machine in INIT.

Per spec §4.1: the per-issue state machine has nine states
(INIT|PLANNED|RED|GREEN|SMOKE|REFACTOR|COMPLETE|BLOCKED|MERGED) and a
transition table describing legal next states for each. J1 ships the
*skeleton* — the enum and the table exist and are consulted, but no
side-effecting transition handlers run.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_phase_enum_has_all_nine_states():
    from atdd.coach.commands.coach import Phase

    expected = {
        "INIT", "PLANNED", "RED", "GREEN", "SMOKE",
        "REFACTOR", "COMPLETE", "BLOCKED", "MERGED",
    }
    assert {p.name for p in Phase} == expected


def test_phase_enum_serializes_to_stable_string():
    from atdd.coach.commands.coach import Phase

    assert Phase.INIT.value == "INIT"
    assert Phase.MERGED.value == "MERGED"
    assert str(Phase.PLANNED) == "PLANNED"


def test_transition_table_covers_every_phase():
    from atdd.coach.commands.coach import Phase, TRANSITION_TABLE

    assert set(TRANSITION_TABLE.keys()) == set(Phase)


def test_transition_table_lifecycle_edges():
    """Per spec §4.1: forward edges, BLOCKED escape hatch, terminal states."""
    from atdd.coach.commands.coach import Phase, TRANSITION_TABLE

    assert Phase.PLANNED in TRANSITION_TABLE[Phase.INIT]
    assert Phase.RED in TRANSITION_TABLE[Phase.PLANNED]
    assert Phase.GREEN in TRANSITION_TABLE[Phase.RED]
    assert Phase.SMOKE in TRANSITION_TABLE[Phase.GREEN]
    assert Phase.REFACTOR in TRANSITION_TABLE[Phase.SMOKE]
    assert Phase.COMPLETE in TRANSITION_TABLE[Phase.REFACTOR]
    assert Phase.MERGED in TRANSITION_TABLE[Phase.COMPLETE]

    for forward in (
        Phase.INIT, Phase.PLANNED, Phase.RED,
        Phase.GREEN, Phase.SMOKE, Phase.REFACTOR,
    ):
        assert Phase.BLOCKED in TRANSITION_TABLE[forward]

    assert TRANSITION_TABLE[Phase.MERGED] == set()


def test_can_transition_uses_table():
    from atdd.coach.commands.coach import Phase, can_transition

    assert can_transition(Phase.INIT, Phase.PLANNED) is True
    assert can_transition(Phase.INIT, Phase.GREEN) is False
    assert can_transition(Phase.MERGED, Phase.INIT) is False


def test_initialize_state_machine_returns_init_phase():
    from atdd.coach.commands.coach import Phase, initialize_state_machine

    sm = initialize_state_machine(issue_number=358)
    assert sm.issue_number == 358
    assert sm.phase is Phase.INIT
    assert sm.history == []


def test_run_main_prints_planned_state_path_without_transitions(capsys):
    """Per acceptance: `atdd coach 358` prints the planned state path
    without executing transitions."""
    from atdd.coach.commands.coach import run

    rc = run(issue_numbers=[358], dry_run=True)
    assert rc == 0

    out = capsys.readouterr().out
    assert "358" in out
    assert "INIT" in out
    assert "PLANNED" in out  # planned path includes downstream phases


def test_run_does_not_attach_watchers_or_dispatch_validators(monkeypatch, capsys):
    """No watcher / validator / observer / spawn / two-phase-commit /
    decision-durability / resume side-effects in J1."""
    import subprocess

    forbidden_calls: list = []

    def _record_subprocess(*args, **kwargs):
        forbidden_calls.append(("subprocess", args, kwargs))
        raise AssertionError(f"subprocess called in J1 skeleton: {args}")

    monkeypatch.setattr(subprocess, "run", _record_subprocess)
    monkeypatch.setattr(subprocess, "Popen", _record_subprocess)
    monkeypatch.setattr(subprocess, "check_call", _record_subprocess)
    monkeypatch.setattr(subprocess, "check_output", _record_subprocess)

    from atdd.coach.commands.coach import run

    rc = run(issue_numbers=[358], dry_run=True)
    assert rc == 0
    assert forbidden_calls == []
