"""Shared test helpers for surface-worker-decisions (hermetic, no cmux)."""
from __future__ import annotations

from atdd.mediate_worker_decisions.surface_worker_decisions.src.application.ports import (
    HookPresence,
)

# The agent kinds the toolkit spawns as claude-family workers (must all surface Bash).
CLAUDE_AGENT_KINDS = ("claude", "claude-glm", "claude-gpt")


class StubProbe:
    """A HookPresenceProbe returning a fixed verdict — for injecting active/inactive."""

    def __init__(self, *, active: bool, reason: str = "") -> None:
        self._presence = HookPresence(active=active, reason=reason)

    def evaluate(self) -> HookPresence:
        return self._presence
