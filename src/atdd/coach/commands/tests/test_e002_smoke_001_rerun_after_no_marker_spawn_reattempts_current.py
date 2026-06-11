# URN: test:drive-state-machine:phase-advance-requires-completion-match:E002-SMOKE-001-rerun-after-no-marker-spawn-reattempts-current
# Acceptance: acc:drive-state-machine:E002-SMOKE-001-rerun-after-no-marker-spawn-reattempts-current
# WMBT: wmbt:drive-state-machine:E002
# Phase: SMOKE
# Harness: smoke
# Layer: application
"""E002-SMOKE-001 — re-running the coach after a no-marker spawn re-attempts the current phase.

Issue #1055, live reproduction. The defect: re-running ``atdd coach <N>`` on a
phase whose worker left no ``done.json`` advances the phase anyway and spawns the
NEXT persona (RED→GREEN, a coder with no RED tests). This SMOKE verifies the
behavior end-to-end through ``drive_single_issue``: a coach re-run after a
current-phase spawn that wrote no completion marker re-attempts the CURRENT phase
on EVERY run and never advances to GREEN.

The RED tester's spawn is rigged to "fail before writing done.json" (its stub
returns HANDLED but no marker is recorded), simulating the cmux Broken-pipe
trigger. Across two sequential re-runs the coach must keep re-attempting RED.

RED until the warm-resume completion-gate is implemented: on current code each
re-run advances RED→GREEN and spawns a coder, so the live #1051 RED-skip
reproduces.
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


def _run_once(runtime_dir, monkeypatch):
    """One coach run warm-resumed at RED with a spawn that writes no done.json."""
    from atdd.coach.commands.coach import Phase
    from atdd.coach.handlers.state_machine import HandlerResult, StateMachine
    from atdd.train.issue_runner import drive_single_issue

    # RED-phase smoke: no live issue/network exists yet, so the two GitHub-label
    # helpers are stubbed to drive the warm-resume re-attempt behavior hermetically.
    # The real-infrastructure upgrade lands when the coder reaches the SMOKE phase.
    monkeypatch.setattr(  # atdd:suppress(tester.smoke.no-collaborator-substitution) UNTIL=2026-09-01
        "atdd.coach.commands.coach._read_current_github_phase",
        lambda _issue: Phase.RED,
    )
    label_swaps: list = []
    monkeypatch.setattr(  # atdd:suppress(tester.smoke.no-collaborator-substitution) UNTIL=2026-09-01
        "atdd.coach.commands.coach._swap_phase_label",
        lambda _issue, phase: label_swaps.append(phase),
    )

    spawn_calls: list = []

    def stub_spawn_no_marker(ctx, transition):
        # Rigged: the RED persona "spawns" but never writes a done.json marker
        # (the cmux Broken-pipe trigger). It reports HANDLED regardless.
        spawn_calls.append((transition.src, transition.dst))
        return HandlerResult.HANDLED

    cfg = _make_cfg()
    sm = StateMachine(issue_number=1051, phase=Phase.INIT)
    rc = drive_single_issue(
        cfg, sm, runtime_dir,
        _spawn_func=stub_spawn_no_marker,
        _max_loop_events=0,
    )
    return rc, sm, spawn_calls, label_swaps


def test_rerun_after_no_marker_spawn_reattempts_current(tmp_path, monkeypatch):
    """Two sequential re-runs both re-attempt RED; neither spawns a GREEN coder."""
    from atdd.coach.commands.coach import Phase

    for run_idx in range(2):
        runtime = tmp_path / f"run_{run_idx}"
        rc, sm, spawn_calls, label_swaps = _run_once(runtime, monkeypatch)

        assert rc == 0, f"run {run_idx}: expected rc=0; got {rc}"

        dsts = [d for _s, d in spawn_calls]
        assert dsts and all(d == Phase.RED for d in dsts), (
            f"run {run_idx}: a re-run with no completion marker must re-attempt the "
            f"CURRENT phase (dst=RED), not advance; got {spawn_calls}"
        )
        assert Phase.GREEN not in dsts, (
            f"run {run_idx}: must never spawn the GREEN coder when RED never "
            f"completed; got {spawn_calls}"
        )
        assert sm.phase == Phase.RED, (
            f"run {run_idx}: SM must stay at RED; got {sm.phase}"
        )
        assert Phase.GREEN not in label_swaps, (
            f"run {run_idx}: label must stay at RED (no RED→GREEN swap); "
            f"got {label_swaps}"
        )
