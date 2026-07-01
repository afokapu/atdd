"""Verdict value object (pure)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_RULE = "coder.duplication.no-intra-layer-code-python"


@dataclass(frozen=True)
class Verdict:
    verdict_id: str
    decided_at: str
    reason: Optional[str] = None

    def is_final(self) -> bool:
        flag = self.reason is not None
        return flag
