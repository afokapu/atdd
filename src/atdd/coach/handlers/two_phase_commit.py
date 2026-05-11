"""Two-phase-commit handler stub — P2 wiring lives here (issue #590 will fill)."""
from __future__ import annotations

from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Transition


def handle(ctx: CoachContext, transition: Transition) -> HandlerResult:
    return HandlerResult.NOOP
