"""Application ports for apply-decision (Protocols only)."""
from __future__ import annotations

from typing import Protocol

from atdd.mediate_worker_decisions.apply_decision.src.domain.application_plan import (
    WorkerInstruction,
)
from atdd.mediate_worker_decisions.apply_decision.src.domain.record import DecisionRecord


class WorkerApplier(Protocol):
    """Narrow seam over agent_control: deliver an instruction to one worker."""

    def apply(self, handle_ref: str, instruction: WorkerInstruction) -> None: ...


class DecisionLedger(Protocol):
    """Append a terminal decision record to the durable ledger."""

    def record(self, record: DecisionRecord) -> None: ...


class AppliedGuard(Protocol):
    """Idempotency memory keyed by the request+verdict idempotency key."""

    def seen(self, key: str) -> bool: ...

    def mark(self, key: str) -> None: ...
