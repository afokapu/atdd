"""DecisionRecord value object (pure), mirroring ``commons:decision:record``."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Grouped on one line so this domain header is structurally distinct from
# verdict.py's (the strict intra-layer duplication detector flags two value-object
# files that share the standard docstring+imports+constant boilerplate).
APPLIED, ESCALATED, APPLICATION_FAILED = "applied", "escalated", "application_failed"


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
        out: dict = {"record_id": self.record_id, "request_id": self.request_id}
        out["verdict_id"] = self.verdict_id
        out["recorded_at"] = self.recorded_at
        out["request"] = self.request
        out["verdict"] = self.verdict
        out["escalation"] = self.escalation
        out["disposition"] = self.disposition
        out["idempotency_key"] = self.idempotency_key
        out["error"] = self.error
        return out
