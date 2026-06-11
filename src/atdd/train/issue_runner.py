"""Per-issue train-runner drive loop (docs/coach-decomposition.md §6.1, Child 8).

This module is the new home of the stateful per-issue orchestration that used to
live in ``atdd.coach.commands.coach``: it drives one issue from INIT through its
lifecycle, draining the watcher / injected-event loop and building the resume
transition action. ``atdd.coach.commands.coach`` keeps ``@deprecated`` compatibility
shims of the same names (``_drive_single_issue`` etc.) that delegate here through
the 3.87.0 soak (§11).

Layer discipline (§3.3): ``atdd.train.*`` MAY import ``atdd.coach.*`` (the policy
+ handler layers), ``atdd.runtime.*`` and ``atdd.integrations.*``; it MUST NOT
import ``atdd.cli`` or ``atdd.observer``. The shared coach helpers
(``_make_coach_context``, ``_swap_phase_label``, ``_read_current_github_phase`` …)
are referenced through the ``coach`` *module object* (``_coach.<name>``) rather than
bound by ``from ... import`` so that callers monkeypatching ``coach.<name>`` (the
existing coach test suite) keep working unchanged during the migration. Those
helpers move into the train/runtime layers in Child 10 (§13.10).
"""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from atdd.coach.commands import coach as _coach

_logger = logging.getLogger("atdd.coach")

# Convenience re-binds for the immutable enum/type the bodies below reference.
Phase = _coach.Phase


def drive_single_issue(
    cfg: "_coach.Config",
    sm: "_coach.StateMachine",
    runtime_dir: Path,
    *,
    _spawn_func: Optional[Callable] = None,
    _two_phase_func: Optional[Callable] = None,
    _injected_events: Optional[list] = None,
    _max_loop_events: Optional[int] = None,
    _run_id_sink: Optional[list] = None,
) -> int:
    """Drive one issue from INIT through the full lifecycle.

    Returns 0 on COMPLETE (or REFACTOR halt without --auto-merge),
    1 on BLOCKED/spawn-failure, 2 on unrecoverable error. (Issue #645 —
    cold-start wiring; moved out of coach.py in Child 8 / #895.)
    """
    from atdd.coach.handlers import spawn as spawn_handler, two_phase_commit as tpc_handler
    from atdd.coach.handlers.state_machine import HandlerResult, Transition
    from atdd.coach.commands.durability import DecisionWriter, transactional_decision
    from atdd.coach.utils.coach_lock import CoachAlreadyRunning, CoachLock

    spawn_h = _spawn_func or spawn_handler.handle
    two_phase_h = _two_phase_func or tpc_handler.handle

    # --- Single-instance guard (E011, issue #724) ---
    _lock = CoachLock(runtime_dir, issue_number=sm.issue_number)
    try:
        _lock.acquire()
    except CoachAlreadyRunning as exc:
        _logger.warning("coach already running for #%d: %s", sm.issue_number, exc,
                        extra={"issue": sm.issue_number})
        print(f"❌ #{sm.issue_number}: {exc}", file=_coach.sys.stderr)
        _coach._write_escalation(cfg.escalation_channel, f"#{sm.issue_number}: {exc}")
        return 1

    try:
        coach_run_id = f"coach-run-{sm.issue_number}-{uuid.uuid4().hex[:8]}"
        if _run_id_sink is not None:
            _run_id_sink.append(coach_run_id)

        ctx = _coach._make_coach_context(cfg, sm.issue_number, coach_run_id, runtime_dir)

        writer = DecisionWriter(runtime_dir=runtime_dir)

        # --- Step 1: Warm-resume or cold-start ---
        current_github_phase = _coach._read_current_github_phase(sm.issue_number)
        is_warm_resume = current_github_phase in _coach._WARM_RESUME_PHASES

        if is_warm_resume:
            sm.history.append(sm.phase)
            sm.phase = current_github_phase
            _logger.info(
                "coach warm-resume",
                extra={"issue": sm.issue_number, "phase": current_github_phase.value,
                       "trigger": "warm-resume"},
            )
            next_phase = _coach._COLD_START_ADVANCE_FROM.get(current_github_phase)
            # #1055 — phase-advance-requires-completion-match. Before advancing
            # current→next, verify the CURRENT phase's worker actually completed
            # (a phase-tagged done.json marker). On a re-run after a spawn that
            # left no done.json (the live #1051 RED-skip), re-attempt the CURRENT
            # phase instead of advancing — and do NOT swap the label forward.
            current_completed = _coach._phase_completion_marker_present(
                runtime_dir, sm.issue_number, current_github_phase
            )
            if next_phase is not None and current_completed:
                warm_t = Transition(current_github_phase, next_phase)
                spawn_result = spawn_h(ctx, warm_t)
                if spawn_result == HandlerResult.ERROR:
                    _logger.error(
                        "coach warm-resume spawn failed",
                        extra={"issue": sm.issue_number,
                               "phase": f"{current_github_phase.value}→{next_phase.value}",
                               "trigger": "warm-resume"},
                    )
                    _coach._write_escalation(
                        cfg.escalation_channel,
                        f"#{sm.issue_number}: spawn failed at {current_github_phase.value}→{next_phase.value}",
                    )
                    sm.history.append(sm.phase)
                    sm.phase = Phase.BLOCKED
                    return 1
                sm.history.append(sm.phase)
                sm.phase = next_phase
                _coach._swap_phase_label(sm.issue_number, next_phase)
                _logger.info(
                    "coach warm-resume advance",
                    extra={"issue": sm.issue_number,
                           "phase": f"{current_github_phase.value}→{next_phase.value}",
                           "trigger": "warm-resume"},
                )
                _coach._try_emit_telemetry(sm.issue_number, current_github_phase, next_phase)
            else:
                # CURRENT phase incomplete (no done.json marker) → re-attempt it:
                # spawn the current phase's persona via Transition(<prev>, current).
                # Leave the SM at current and do NOT swap the label (#1055).
                prev_phase = _coach._PHASE_PREDECESSOR.get(
                    current_github_phase, current_github_phase
                )
                reattempt_t = Transition(prev_phase, current_github_phase)
                spawn_result = spawn_h(ctx, reattempt_t)
                if spawn_result == HandlerResult.ERROR:
                    _logger.error(
                        "coach warm-resume re-attempt spawn failed",
                        extra={"issue": sm.issue_number,
                               "phase": f"{prev_phase.value}→{current_github_phase.value}",
                               "trigger": "warm-resume-reattempt"},
                    )
                    _coach._write_escalation(
                        cfg.escalation_channel,
                        f"#{sm.issue_number}: spawn failed re-attempting {current_github_phase.value}",
                    )
                    sm.history.append(sm.phase)
                    sm.phase = Phase.BLOCKED
                    return 1
                _logger.info(
                    "coach warm-resume re-attempt",
                    extra={"issue": sm.issue_number,
                           "phase": f"{prev_phase.value}→{current_github_phase.value}",
                           "trigger": "warm-resume-reattempt"},
                )
        else:
            # Cold start: write INIT→PLANNED decision, ensure worktree, spawn planner.
            init_record = _coach._make_phase_transition_record(
                coach_run_id, sm.issue_number, Phase.INIT, Phase.PLANNED)
            with transactional_decision(writer, init_record):
                pass  # decision is written by the CM; no blocking action here

            # Ensure the issue's git worktree exists before spawning (#795 incident).
            if not cfg.dry_run:
                worktree = _coach._ensure_issue_worktree(ctx)
                if worktree is None:
                    _logger.error(
                        "coach cold-start worktree creation failed",
                        extra={"issue": sm.issue_number, "phase": "INIT→PLANNED", "trigger": "cold-start"},
                    )
                    _coach._write_escalation(
                        cfg.escalation_channel,
                        f"#{sm.issue_number}: worktree creation failed at INIT→PLANNED",
                    )
                    sm.history.append(sm.phase)
                    sm.phase = Phase.BLOCKED
                    return 1

            spawn_result = spawn_h(ctx, Transition(Phase.INIT, Phase.PLANNED))
            if spawn_result == HandlerResult.ERROR:
                _logger.error(
                    "coach cold-start spawn failed",
                    extra={"issue": sm.issue_number, "phase": "INIT→PLANNED", "trigger": "cold-start"},
                )
                _coach._write_escalation(cfg.escalation_channel, f"#{sm.issue_number}: spawn failed at INIT→PLANNED")
                sm.history.append(sm.phase)
                sm.phase = Phase.BLOCKED
                return 1

            sm.history.append(sm.phase)
            sm.phase = Phase.PLANNED
            _logger.info(
                "coach cold-start advance",
                extra={"issue": sm.issue_number, "phase": "INIT→PLANNED", "trigger": "cold-start"},
            )
            _coach._try_emit_telemetry(sm.issue_number, Phase.INIT, Phase.PLANNED)

        # --- Step 2: Event-driven loop ---
        if _injected_events is not None:
            _process_injected_events(ctx, sm, _injected_events, writer, spawn_h)
        elif _max_loop_events == 0:
            pass  # test seam: skip event loop entirely
        else:
            ttl_secs = cfg.no_progress_ttl * 60 if cfg.no_progress_ttl else None
            _process_watcher_events(ctx, sm, runtime_dir, cfg, writer, spawn_h,
                                    max_events=_max_loop_events,
                                    no_progress_ttl_seconds=ttl_secs)

        # --- Step 5: Handle terminal states ---
        if sm.phase == Phase.BLOCKED:
            return 1

        if sm.phase == Phase.REFACTOR and not cfg.auto_merge:
            # R5: stop at REFACTOR when auto-merge is off; escalate for operator review
            msg = (
                f"#{sm.issue_number} reached REFACTOR. "
                f"Run: atdd coach {sm.issue_number} --auto-merge to proceed."
            )
            _coach._write_escalation(cfg.escalation_channel, msg)
            _logger.info(
                "coach REFACTOR escalated",
                extra={"issue": sm.issue_number, "phase": "REFACTOR", "trigger": "escalate-no-auto-merge"},
            )
            return 0

        if sm.phase == Phase.COMPLETE:
            t_complete = Transition(Phase.COMPLETE, Phase.MERGED)
            result = two_phase_h(ctx, t_complete)
            if result == HandlerResult.HANDLED:
                sm.history.append(sm.phase)
                sm.phase = Phase.MERGED
                _logger.info(
                    "coach auto-merge advance",
                    extra={"issue": sm.issue_number, "phase": "COMPLETE→MERGED", "trigger": "auto-merge"},
                )
                _coach._try_emit_telemetry(sm.issue_number, Phase.COMPLETE, Phase.MERGED)
            elif result == HandlerResult.ERROR:
                _coach._write_escalation(cfg.escalation_channel, f"#{sm.issue_number}: two-phase commit failed")
                return 1
            # NOOP → no auto-merge; COMPLETE persists pending operator action

        return 0
    finally:
        _lock.release()


def _process_injected_events(
    ctx: "_coach.CoachContext",
    sm: "_coach.StateMachine",
    events: list,
    writer: "_coach.DecisionWriter",
    spawn_h: Callable,
) -> None:
    """Process a pre-programmed event list (test seam for cold-start, issue #645)."""
    from atdd.coach.handlers.state_machine import HandlerResult, Transition
    from atdd.coach.commands.durability import transactional_decision

    for event in events:
        if sm.phase in (Phase.COMPLETE, Phase.MERGED, Phase.BLOCKED):
            break
        t = _coach._cold_start_proposed_transition(sm, event)
        if t is None:
            continue
        record = _coach._make_phase_transition_record(
            ctx.coach_run_id, ctx.issue_number, t.src, t.dst
        )
        with transactional_decision(writer, record):
            pass
        sm.history.append(sm.phase)
        sm.phase = t.dst
        _coach._swap_phase_label(ctx.issue_number, t.dst)
        _logger.info(
            "coach injected event advance",
            extra={"issue": ctx.issue_number, "phase": f"{t.src.value}→{t.dst.value}",
                   "trigger": event.get("event_type", "injected")},
        )
        _coach._try_emit_telemetry(ctx.issue_number, t.src, t.dst)
        # Spawn next persona for this transition
        spawn_result = spawn_h(ctx, t)
        if spawn_result == HandlerResult.ERROR:
            _logger.error(
                "coach injected event spawn failed",
                extra={"issue": ctx.issue_number, "phase": f"{t.src.value}→{t.dst.value}"},
            )
            sm.history.append(sm.phase)
            sm.phase = Phase.BLOCKED
            break


def _process_watcher_events(
    ctx: "_coach.CoachContext",
    sm: "_coach.StateMachine",
    runtime_dir: Path,
    cfg: "_coach.Config",
    writer: "_coach.DecisionWriter",
    spawn_h: Callable,
    *,
    max_events: Optional[int] = None,
    no_progress_ttl_seconds: Optional[int] = None,
) -> None:
    """Block on WatcherEventLoop until SM reaches a terminal state (production path)."""
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.commands.runtime_watcher import RuntimeWatcher
    from atdd.coach.handlers.state_machine import HandlerResult, Transition
    from atdd.coach.commands.durability import transactional_decision

    # #708 link 3: the watcher must scan the dispatched persona's worktree
    # runtime, not the coach cwd's. The CoachEventQueue stays on the coach's
    # own runtime_dir (coach-side durability) — only the watcher's scan root
    # follows the persona.
    watch_runtime = _coach._watcher_runtime_dir(ctx, runtime_dir)
    queue = CoachEventQueue(runtime_dir=runtime_dir)
    watcher = RuntimeWatcher(runtime_dir=watch_runtime, queue=queue)
    # #711: baseline at dispatch time so a stale done.json (or any runtime
    # file) left by a prior coach run is recorded as already-seen and is not
    # emitted as new on the first scan — only post-dispatch writes advance
    # the phase.
    watcher.baseline()
    watcher.start()
    events_processed = 0
    last_advance_at = time.monotonic()

    try:
        while sm.phase not in (Phase.COMPLETE, Phase.MERGED, Phase.BLOCKED):
            if max_events is not None and events_processed >= max_events:
                break
            event = queue.get(timeout=5.0)
            if event is None:
                # Idle tick — check no-progress TTL (E011, issue #724).
                if no_progress_ttl_seconds and _coach._check_no_progress_ttl(
                    last_advance_at,
                    no_progress_ttl_seconds,
                    cfg.escalation_channel,
                    ctx.issue_number,
                    sm.phase,
                ):
                    break
                continue
            events_processed += 1
            t = _coach._cold_start_proposed_transition(sm, event)
            if t is None:
                continue
            record = _coach._make_phase_transition_record(
                ctx.coach_run_id, ctx.issue_number, t.src, t.dst
            )
            with transactional_decision(writer, record):
                pass
            sm.history.append(sm.phase)
            sm.phase = t.dst
            _coach._swap_phase_label(ctx.issue_number, t.dst)
            last_advance_at = time.monotonic()
            _logger.info(
                "coach watcher event advance",
                extra={"issue": ctx.issue_number, "phase": f"{t.src.value}→{t.dst.value}",
                       "trigger": event.get("event_type", "watcher")},
            )
            _coach._try_emit_telemetry(ctx.issue_number, t.src, t.dst)
            spawn_result = spawn_h(ctx, t)
            if spawn_result == HandlerResult.ERROR:
                _logger.error(
                    "coach watcher event spawn failed",
                    extra={"issue": ctx.issue_number, "phase": f"{t.src.value}→{t.dst.value}"},
                )
                sm.history.append(sm.phase)
                sm.phase = Phase.BLOCKED
                break
    finally:
        watcher.stop()
        try:
            watcher.persist_checkpoint()
        except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-01
            pass


def make_resume_transition_action(
    cfg: "_coach.Config",
    runtime_dir: Path,
    *,
    multiplexer_backend: Optional[object] = None,
    worktree_override: Optional[Path] = None,
) -> Callable[[int, str, str], dict]:
    """Build the real per-transition orchestration action for ``--resume``.

    Mirrors the cold-start spawn dispatch (#645): for each pending transition the
    resumed runner walks, spawn that phase's persona via the same handler
    ``drive_single_issue`` uses. A transition whose spawn handler returns ERROR
    raises, so ``ResumeRunner`` BLOCKs/escalates instead of paper-stamping the
    issue to COMPLETE (issue #734).
    """
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.handlers.state_machine import HandlerResult, Transition

    def _action(issue: int, src: str, dst: str) -> dict:
        ctx = _coach._make_coach_context(
            cfg,
            issue,
            cfg.resume or f"coach-resume-{issue}",
            runtime_dir,
            multiplexer_backend=multiplexer_backend,
            worktree_override=worktree_override,
        )
        transition = Transition(Phase(src), Phase(dst))
        result = spawn_handler.handle(ctx, transition)
        if result == HandlerResult.ERROR:
            raise RuntimeError(
                f"#{issue}: resume orchestration failed at {src}->{dst} "
                f"(spawn handler returned ERROR)"
            )
        return {"transitioned": True, "new_phase": dst}

    return _action


__all__ = [
    "drive_single_issue",
    "_process_injected_events",
    "_process_watcher_events",
    "make_resume_transition_action",
]
