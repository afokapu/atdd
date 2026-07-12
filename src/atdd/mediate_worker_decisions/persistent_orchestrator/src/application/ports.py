"""Ports for the persistent orchestrator (application boundary).

The supervisor loop is pure CORE: it depends only on these injected seams, never
on the real cmux send-key / live-launch runtime (that is the provider's, ext#28/
#29). Tests inject fakes so the loop is hermetic and deterministic — no real
clock, no real cmux.
"""
from __future__ import annotations

from typing import Protocol

from atdd.mediate_worker_decisions.persistent_orchestrator.src.domain.phase_snapshot import (
    PhaseSnapshot,
)


class PhasePoller(Protocol):
    """Reads the work item's current phase and done-signal (the provider's poll)."""

    def poll(self, work_item_id: str) -> PhaseSnapshot: ...


class PhaseDriver(Protocol):
    """Drives the next phase transition (swap the label / re-dispatch the persona)."""

    def advance(self, work_item_id: str, from_phase: str) -> None: ...


class Sleeper(Protocol):
    """Paces the poll loop; injected so tests stay instant (no real clock)."""

    def sleep(self, seconds: float) -> None: ...
