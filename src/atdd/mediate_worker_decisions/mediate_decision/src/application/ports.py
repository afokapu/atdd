"""Application ports for mediate-decision (Protocols only)."""
from __future__ import annotations

from typing import Protocol

from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    Escalation,
    Verdict,
)


class CoachClient(Protocol):
    """Presents a request to the coach surface and reads its current reply text."""

    def present(self, request_text: str) -> None: ...

    def read_reply(self) -> str: ...


class Clock(Protocol):
    """Injected time source so the timeout path is deterministic under test."""

    def now(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class VerdictSink(Protocol):
    def emit(self, verdict: Verdict) -> None: ...


class EscalationSink(Protocol):
    def emit(self, escalation: Escalation) -> None: ...
