"""Application ports for sense-decision (Protocols only — no concrete I/O).

Integration adapters implement these; the use case depends only on these
abstractions, keeping the cmux/runtime dependencies out of the application and
domain tiers (four-tier dependency rule).
"""
from __future__ import annotations

from typing import Optional, Protocol

from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    DecisionRequest,
    WorkerRef,
)


class SurfaceReader(Protocol):
    """Reads (ANSI-stripped) scrollback text from a worker surface."""

    def read(self, surface_id: str) -> str: ...


class WorkerRegistry(Protocol):
    """Resolves a cmux surface id to exactly one registered worker, or None."""

    def resolve(self, surface_id: str) -> Optional[WorkerRef]: ...


class RequestSink(Protocol):
    """Durably records an emitted decision request (the internal seam to mediate)."""

    def emit(self, request: DecisionRequest) -> None: ...
