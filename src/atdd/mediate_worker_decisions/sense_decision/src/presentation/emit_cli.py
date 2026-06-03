"""`atdd decision emit` entrypoint — inject a decision request without cmux.

Lets ATDD validators / lifecycle scripts raise a decision directly. It MUST
serialize through the same RequestSink as the notify hook so the two entry
paths cannot diverge (WMBT D001); only ``provenance.source`` differs.
"""
from __future__ import annotations

from typing import Callable, List, Optional

from atdd.mediate_worker_decisions.sense_decision.src.application.ports import RequestSink
from atdd.mediate_worker_decisions.sense_decision.src.application.sense_use_case import (
    SOURCE_EMIT,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    DecisionPrompt,
    DecisionRequest,
    Option,
    WorkerRef,
)


def emit_request(
    *,
    sink: RequestSink,
    surface_id: str,
    question: str,
    options: List[Option],
    id_factory: Callable[[], str],
    clock: Callable[[], str],
    run_id: Optional[str] = None,
) -> DecisionRequest:
    request = DecisionRequest(
        request_id=id_factory(),
        worker=WorkerRef(surface_id=surface_id, run_id=run_id),
        prompt=DecisionPrompt(
            raw_text=question, question=question, options=tuple(options)
        ),
        source=SOURCE_EMIT,
        created_at=clock(),
        notification_hash=None,
    )
    sink.emit(request)
    return request
