"""Decisions handler — J3 wiring (issue #586).

Appends one ``coach-decision.schema.json``-conforming record to
``decisions.jsonl`` for every state transition, before any side-effect
runs.

Spec §4.5 — durable-before-action discipline:
- Write completes (fsync) before yielding to the next handler.
- If the write fails: retry 3× with 1 s / 2 s / 4 s exponential backoff.
- On exhaustion: log to stderr, return ERROR (caller sets BLOCKED state).

``coach_run_id`` and ``runtime_dir`` come from ``CoachContext``; both are
populated by the J3 wiring in ``coach.py`` at startup.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Transition

_RUNTIME_ROOT = Path(".atdd") / "runtime"
_BACKOFF_DELAYS = (1, 2, 4)
_MAX_ATTEMPTS = len(_BACKOFF_DELAYS) + 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def handle(ctx: CoachContext, transition: Transition) -> HandlerResult:
    if ctx.dry_run:
        return HandlerResult.NOOP

    from atdd.coach.commands.durability import DecisionWriter, transactional_decision

    runtime_dir = ctx.runtime_dir if ctx.runtime_dir is not None else _RUNTIME_ROOT
    record = {
        "decision_id": (
            f"{ctx.coach_run_id}:#{ctx.issue_number}"
            f":{transition.src.value}->{transition.dst.value}"
        ),
        "timestamp": _now(),
        "coach_run_id": ctx.coach_run_id,
        "issue_number": ctx.issue_number,
        "decision_type": "phase-transition",
        "inputs": {
            "current_phase": transition.src.value,
            "target_phase": transition.dst.value,
        },
        "outcome": {
            "transitioned": True,
            "new_phase": transition.dst.value,
        },
    }

    writer = DecisionWriter(runtime_dir=runtime_dir)
    last_exc: OSError | None = None

    for attempt in range(_MAX_ATTEMPTS):
        if attempt > 0:
            time.sleep(_BACKOFF_DELAYS[attempt - 1])
        try:
            with transactional_decision(writer, record) as run_action:
                return HandlerResult.HANDLED if run_action else HandlerResult.NOOP
        except OSError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-10-31
            last_exc = exc

    print(
        f"decisions: write failed after {_MAX_ATTEMPTS} attempts: {last_exc}",
        file=sys.stderr,
    )
    return HandlerResult.ERROR
