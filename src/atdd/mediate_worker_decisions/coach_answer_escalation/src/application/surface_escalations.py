"""``atdd coach status`` — surface still-unanswered escalations (WMBT L008).

The read half of the recovery loop (``atdd coach answer`` is the write half, see
``answer_escalation``). The daemon escalates a governance sign-off into
``escalations.jsonl`` with no auto-reply (C004/C007), so without surfacing the
operator is never told there is something to answer and the worker stalls. This
use case joins the escalation ledger records (each carrying a ``request_id``)
against the pending Feed items and returns the UNANSWERED escalations, enriched
with their prompt/options for display. Once the operator answers, the
escalation's ``request_id`` is no longer pending in the Feed and it is omitted.

The join itself is the pure domain function ``list_unanswered_escalations``; this
application use case wires it to the two real sources (an escalation-ledger
reader and a ``FeedSource``) behind ports, exactly as ``AnswerEscalationUseCase``
wires ``plan_answer``.
"""
from __future__ import annotations

from typing import Any, List, Mapping, Protocol

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.application.ports import (
    FeedSource,
)
from atdd.mediate_worker_decisions.coach_answer_escalation.src.domain.escalation_surfacing import (
    UnansweredEscalation,
    list_unanswered_escalations,
)


class EscalationRecordSource(Protocol):
    """Port: reads the escalation ledger records (each carrying a ``request_id``)."""

    def read_all(self) -> List[Mapping[str, Any]]:
        ...


class SurfaceEscalationsUseCase:
    """Join escalation ledger records with pending Feed items → unanswered list."""

    def __init__(
        self, *, source: FeedSource, escalations: EscalationRecordSource
    ) -> None:
        self._source = source
        self._escalations = escalations

    def surface(self) -> List[UnansweredEscalation]:
        """Return the still-unanswered escalations, in ledger order."""
        records = self._escalations.read_all()
        return list_unanswered_escalations(records, self._source.list_pending())
