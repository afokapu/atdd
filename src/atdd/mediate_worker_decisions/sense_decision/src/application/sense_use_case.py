"""Sense use case: resolve worker -> read surface -> parse prompt -> emit request.

Orchestration only. All I/O is behind the ports; ids/timestamps are injected so
the use case is deterministic under test.
"""
from __future__ import annotations

from typing import Callable, Optional

from atdd.mediate_worker_decisions.sense_decision.src.application.ports import (
    RequestSink,
    SurfaceReader,
    WorkerRegistry,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    DecisionRequest,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.prompt_parser import (
    parse_prompt,
)

SOURCE_NOTIFICATION = "cmux_notification"
SOURCE_EMIT = "emit_cli"


class SenseDecisionUseCase:
    def __init__(
        self,
        reader: SurfaceReader,
        registry: WorkerRegistry,
        sink: RequestSink,
        id_factory: Callable[[], str],
        clock: Callable[[], str],
    ) -> None:
        self._reader = reader
        self._registry = registry
        self._sink = sink
        self._id = id_factory
        self._now = clock

    def sense(
        self,
        surface_id: str,
        source: str,
        notification_hash: Optional[str] = None,
    ) -> Optional[DecisionRequest]:
        """Return the emitted request, or None when there is nothing to route.

        Returns None (no emit) when the surface does not map to a worker or when
        the surface text is not a genuine decision prompt — never a fabricated
        request (WMBT D001/C001).
        """
        worker = self._registry.resolve(surface_id)
        if worker is None:
            return None

        prompt = parse_prompt(self._reader.read(surface_id))
        if prompt is None:
            return None

        request = DecisionRequest(
            request_id=self._id(),
            worker=worker,
            prompt=prompt,
            source=source,
            created_at=self._now(),
            notification_hash=notification_hash,
        )
        self._sink.emit(request)
        return request
