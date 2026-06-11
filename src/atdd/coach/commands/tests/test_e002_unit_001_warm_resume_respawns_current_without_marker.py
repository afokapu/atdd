# URN: test:drive-state-machine:phase-advance-requires-completion-match:E002-UNIT-001-warm-resume-respawns-current-without-marker
# Acceptance: acc:drive-state-machine:E002-UNIT-001-warm-resume-respawns-current-without-marker
# WMBT: wmbt:drive-state-machine:E002
# Phase: RED
# Harness: unit
# Layer: application
"""E002-UNIT-001 — warm-resume re-spawns the CURRENT phase when no completion marker exists.

Issue #1055. The phase-skip defect: warm-resume in
``src/atdd/train/issue_runner.py`` unconditionally computes
``next_phase = _COLD_START_ADVANCE_FROM[current]`` and spawns the NEXT persona,
never checking whether the CURRENT phase's worker actually completed. So an issue
warm-resumed at RED after a transient tester-spawn failure (cmux Broken-pipe, no
``done.json`` written) advances RED→GREEN and spawns a coder with no RED tests to
make pass (reproduced 3× live on #1051).

The fix: when no completion marker for the CURRENT phase exists, warm-resume must
re-attempt the current phase (a Transition whose ``dst`` is the current phase),
NOT advance to the next one — and must NOT swap the GitHub label forward.

RED until the warm-resume completion-gate is implemented: on current code the
warm-resume advances unconditionally, so ``dst`` is GREEN and the label is swapped
to GREEN.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def _make_cfg(*, issue_numbers=(1051,), dry_run: bool = True):
    from atdd.coach.commands.coach import Config
    return Config(
        issue_numbers=list(issue_numbers),
        dry_run=dry_run,
        skip_review=True,
    )


def test_warm_resume_without_red_marker_reattempts_current(tmp_path, monkeypatch):
    """Warm-resume at RED with NO RED completion marker re-spawns the current phase.

    runtime_dir has no ``agents/`` markers at all (the RED tester never wrote a
    done.json). Expected new behavior: spawn a Transition whose ``dst`` is RED
    (re-attempt the current phase), leave the SM at RED, and do NOT swap the
    label to GREEN.
    """
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

    assert rc == 0, f"Expected rc=0; got {rc}"

    # The single warm-resume spawn must RE-ATTEMPT the current phase: dst == RED.
    assert spawn_calls, "warm-resume must spawn at least once"
    dsts = [d for _s, d in spawn_calls]
    assert all(d == Phase.RED for d in dsts), (
        f"Without a RED completion marker, warm-resume must re-attempt the CURRENT "
        f"phase (dst=RED), not advance; got spawn transitions {spawn_calls}"
    )
    assert Phase.GREEN not in dsts, (
        f"Must NOT spawn the GREEN persona when RED never completed; got {spawn_calls}"
    )

    # The SM must stay at RED (no advance to GREEN).
    assert sm.phase == Phase.RED, (
        f"Expected sm.phase to remain RED (re-attempt); got {sm.phase}"
    )

    # The GitHub label must NOT be advanced to GREEN.
    assert Phase.GREEN not in label_swaps, (
        f"Label must not be swapped to GREEN without a RED completion marker; "
        f"label_swaps={label_swaps}"
    )
