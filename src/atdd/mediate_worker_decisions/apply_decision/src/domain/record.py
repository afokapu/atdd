"""DecisionRecord value object (pure), mirroring ``commons:decision:record``."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

APPLIED = "applied"
ESCALATED = "escalated"
APPLICATION_FAILED = "application_failed"


@dataclass(frozen=True)
class DecisionRecord:
    record_id: str
    request_id: str
    recorded_at: str
    disposition: str  # APPLIED | ESCALATED | APPLICATION_FAILED
    idempotency_key: str
    verdict_id: Optional[str] = None
    request: Optional[dict] = None
    verdict: Optional[dict] = None
    escalation: Optional[dict] = None
    error: Optional[str] = None

    def to_contract(self) -> dict:
        return {
            "record_id": self.record_id,
            "request_id": self.request_id,
            "verdict_id": self.verdict_id,
            "recorded_at": self.recorded_at,
            "request": self.request,
            "verdict": self.verdict,
            "escalation": self.escalation,
            "disposition": self.disposition,
            "idempotency_key": self.idempotency_key,
            "error": self.error,
        }
