"""Pure safety classifier: a decision request -> SAFE | HUMAN_REQUIRED (no I/O).

Examines the question and every option label. A single dangerous option taints
the whole request — the human decides, not the coach (WMBT C002).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from atdd.mediate_worker_decisions.mediate_decision.src.domain.danger_rules import (
    match_danger,
)

SAFE = "safe"
HUMAN_REQUIRED = "human_required"


@dataclass(frozen=True)
class SafetyClass:
    classification: str  # SAFE | HUMAN_REQUIRED
    matched_rule: Optional[str] = None

    @property
    def is_safe(self) -> bool:
        return self.classification == SAFE


def classify(question: str, option_labels: Iterable[str]) -> SafetyClass:
    haystack = " \n ".join([question, *option_labels])
    matched = match_danger(haystack)
    if matched is None:
        return SafetyClass(SAFE)
    return SafetyClass(HUMAN_REQUIRED, matched_rule=matched)
