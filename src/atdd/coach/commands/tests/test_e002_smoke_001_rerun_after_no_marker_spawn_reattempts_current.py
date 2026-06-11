# URN: test:drive-state-machine:phase-advance-requires-completion-match:E002-SMOKE-001-rerun-after-no-marker-spawn-reattempts-current
# Acceptance: acc:drive-state-machine:E002-SMOKE-001-rerun-after-no-marker-spawn-reattempts-current
# WMBT: wmbt:drive-state-machine:E002
# Phase: SMOKE
# Harness: smoke
# Layer: application
"""E002-SMOKE-001 — re-running the coach after a no-marker spawn re-attempts the current phase.

Issue #1055, live reproduction of the #1051 RED-skip. The defect: re-running
``atdd coach <N>`` on a phase whose worker left no ``done.json`` advances the
phase anyway and spawns the NEXT persona (RED→GREEN, a coder with no RED tests).

This SMOKE drives the REAL ``train.issue_runner.drive_single_issue`` warm-resume
path end-to-end against a real temp ``runtime_dir`` with a real ``StateMachine``.
None of the subject's collaborators are substituted: the GitHub boundary
(``_read_current_github_phase`` / ``_swap_phase_label``) is exercised for real
through a stand-in ``gh`` binary placed on ``PATH`` (environment setup — the
canonical way to smoke a subprocess boundary), and the warm-resume completion
gate (``_phase_completion_marker_present``) runs against the real filesystem
(no ``agents/<persona>-<issue>-*/done.json`` exists, so the current phase is
genuinely incomplete). The only legitimate test seam used is ``_spawn_func`` —
to capture the Transition the runner spawns — and ``_max_loop_events=0`` to stop
after the warm-resume decision.

Asserted behavior (the fix): across two sequential re-runs the coach re-attempts
the CURRENT phase (spawn ``Transition(<prev>, RED)``, dst == RED) and never
advances to GREEN nor edits the GitHub label forward to ``atdd:GREEN``.
"""
from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.platform]


# A real `gh` stand-in: it logs every invocation (so the test can prove the
# real subprocess boundary was crossed) and answers `issue view` with a RED
# phase label. `issue edit` (the label swap) succeeds silently — its presence
# in the call log is what a forward swap to atdd:GREEN would look like.
_FAKE_GH = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$GH_CALL_LOG"
if [ "$1" = "issue" ] && [ "$2" = "view" ]; then
  printf '%s\\n' '["atdd:RED","atdd-issue"]'
  exit 0
fi
exit 0
"""


def _install_fake_gh(tmp_path, monkeypatch):
    """Put a stand-in ``gh`` on PATH (allowed environment setup). Returns the call log path."""
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    gh = bindir / "gh"
    gh.write_text(_FAKE_GH)
    gh.chmod(0o755)
    call_log = tmp_path / "gh_calls.log"
    monkeypatch.setenv("GH_CALL_LOG", str(call_log))
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    return call_log


def test_rerun_after_no_marker_spawn_reattempts_current(tmp_path, monkeypatch):
    """Two sequential re-runs both re-attempt RED; neither spawns a GREEN coder nor swaps the label."""
    from atdd.coach.commands.coach import Config, Phase
    from atdd.coach.handlers.state_machine import HandlerResult, StateMachine
    from atdd.train.issue_runner import drive_single_issue

    call_log = _install_fake_gh(tmp_path, monkeypatch)

    cfg = Config(issue_numbers=[1051], dry_run=True, skip_review=True)

    for run_idx in range(2):
        # Fresh runtime dir per run: NO agents/<persona>-1051-*/done.json marker
        # exists, so the real completion gate sees RED as incomplete.
        runtime = tmp_path / f"run_{run_idx}"
        sm = StateMachine(issue_number=1051, phase=Phase.INIT)

        spawn_calls: list = []

        def capture_spawn(ctx, transition):
            # The rigged RED persona "spawns" but writes no done.json marker
            # (the cmux Broken-pipe trigger). It reports HANDLED regardless.
            spawn_calls.append((transition.src, transition.dst))
            return HandlerResult.HANDLED

        rc = drive_single_issue(
            cfg, sm, runtime,
            _spawn_func=capture_spawn,
            _max_loop_events=0,
        )

        assert rc == 0, f"run {run_idx}: expected rc=0; got {rc}"

        # The real subprocess boundary was crossed: gh issue view was invoked.
        log_text = call_log.read_text(encoding="utf-8")
        assert "issue view" in log_text, (
            f"run {run_idx}: expected the real _read_current_github_phase to invoke "
            f"`gh issue view`; call log was:\n{log_text}"
        )

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

    # Across both re-runs the label was never swapped forward to GREEN: the real
    # _swap_phase_label would have issued `gh issue edit ... --add-label atdd:GREEN`.
    full_log = call_log.read_text(encoding="utf-8")
    assert "atdd:GREEN" not in full_log, (
        f"label must stay at RED (no RED→GREEN swap); gh call log was:\n{full_log}"
    )
