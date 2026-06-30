"""DecisionRecord value object (pure)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_RULE = "coder.duplication.no-intra-layer-code-python"


@dataclass(frozen=True)
class DecisionRecord:
    record_id: str
    request_id: str

    def to_contract(self) -> dict:
        out: dict = {}
        out["record_id"] = self.record_id
        return out
