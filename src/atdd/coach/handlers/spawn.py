"""Spawn handler stub — K1 wiring lives here (issue #585 will fill)."""
from __future__ import annotations

from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Transition


def handle(ctx: CoachContext, transition: Transition) -> HandlerResult:
    return HandlerResult.NOOP
