"""Presentation seam for apply-decision."""
from __future__ import annotations

from atdd.mediate_worker_decisions.apply_decision.src.domain.record import DecisionRecord


def record_disposition(record: DecisionRecord) -> str:
    return record.disposition
