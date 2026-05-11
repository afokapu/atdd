"""Handler package for coach v9 (issue #591 split).

Re-exports the state-machine symbols so consumers can import from either
`atdd.coach.handlers` or `atdd.coach.handlers.state_machine`.
"""
from atdd.coach.handlers.state_machine import (
    CoachContext,
    HandlerResult,
    Phase,
    PLANNED_PATH,
    StateMachine,
    Transition,
    TRANSITION_TABLE,
    can_transition,
    initialize_state_machine,
)

__all__ = [
    "CoachContext",
    "HandlerResult",
    "Phase",
    "PLANNED_PATH",
    "StateMachine",
    "Transition",
    "TRANSITION_TABLE",
    "can_transition",
    "initialize_state_machine",
]
