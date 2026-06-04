"""Ports for surface-worker-decisions (application boundary).

``HookPresenceProbe`` confirms the cmux wrapper's PermissionRequest->feed hook
path will be active for a worker at launch — so a surfaced decision actually
publishes. Injected so the resolve use case stays unit-testable without cmux.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class HookPresence:
    """Whether the Feed-publishing hook path is active, and why not when it isn't."""

    active: bool
    reason: str


class HookPresenceProbe(Protocol):
    """Reports whether the cmux wrapper will inject the PermissionRequest->feed hook."""

    def evaluate(self) -> HookPresence: ...
