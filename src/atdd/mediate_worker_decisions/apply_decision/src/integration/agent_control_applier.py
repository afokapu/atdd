"""WorkerApplier adapter over the existing runtime.agent_control controller.

Deliberately narrow: it uses only ``deliver_prompt`` (the one capability apply
needs), not the whole AgentController surface, so this feature stays decoupled
from runtime internals it does not use.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.apply_decision.src.domain.application_plan import (
    WorkerInstruction,
)


class AgentControlApplier:
    def __init__(self, controller: object) -> None:
        # controller: atdd.runtime.agent_control.AgentController (duck-typed).
        self._controller = controller

    def apply(self, handle_ref: str, instruction: WorkerInstruction) -> None:
        # deliver_prompt injects AND submits the answer to the worker agent.
        self._controller.deliver_prompt(handle_ref, instruction.text)


class InMemoryAppliedGuard:
    """AppliedGuard backed by a process-local set (single-coach scope)."""

    def __init__(self) -> None:
        self._seen: set = set()

    def seen(self, key: str) -> bool:
        return key in self._seen

    def mark(self, key: str) -> None:
        self._seen.add(key)
