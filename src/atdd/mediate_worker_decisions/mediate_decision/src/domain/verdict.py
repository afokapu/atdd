"""Verdict / Escalation value objects (pure), mirroring their contracts.

``commons:decision:verdict`` (internal) and ``commons:decision:escalation``
(external). disposition encodes the safety guarantee in the data itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

AUTO_APPLY = "auto_apply"
HUMAN_REQUIRED = "human_required"

SOURCE_COACH = "coach"
SOURCE_SAFETY_GATE = "safety_gate"

CAUSE_DANGEROUS = "dangerous_action"
CAUSE_TIMEOUT = "coach_timeout"
CAUSE_UNPARSEABLE = "coach_unparseable"


@dataclass(frozen=True)
class Verdict:
    verdict_id: str
    request_id: str
    decided_at: str
    disposition: str  # AUTO_APPLY | HUMAN_REQUIRED
    source: str  # SOURCE_COACH | SOURCE_SAFETY_GATE
    selected_option_id: Optional[str] = None
    reason: str = ""

    def to_contract(self) -> dict:
        return {
            "verdict_id": self.verdict_id,
            "request_id": self.request_id,
            "decided_at": self.decided_at,
            "disposition": self.disposition,
            "selected_option_id": self.selected_option_id,
            "reason": self.reason,
            "source": self.source,
        }


@dataclass(frozen=True)
class Escalation:
    escalation_id: str
    request_id: str
    raised_at: str
    cause: str  # CAUSE_DANGEROUS | CAUSE_TIMEOUT | CAUSE_UNPARSEABLE
    safety_class: Optional[str] = None
    human_channel_ref: Optional[str] = None

    def to_contract(self) -> dict:
        out = {
            "escalation_id": self.escalation_id,
            "request_id": self.request_id,
            "raised_at": self.raised_at,
            "cause": self.cause,
        }
        if self.safety_class is not None:
            out["safety_class"] = self.safety_class
        if self.human_channel_ref is not None:
            out["human_channel_ref"] = self.human_channel_ref
        return out
