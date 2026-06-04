"""Feature composition root for sense-decision (SPEC-CODER-COMP-0004).

Wires the four tiers — domain (via the use case), application, integration
adapters, presentation entrypoints. The production screen-scrape wiring
(``build_sense_use_case_from_repo`` over ``CmuxSurfaceReader`` /
``RegistryWorkerLookup``) was removed in 3.90.0; the cmux Feed integration
(``atdd.mediate_worker_decisions.bridge_cmux_feed``) is the channel now.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

# application
from atdd.mediate_worker_decisions.sense_decision.src.application.ports import (
    RequestSink,
    SurfaceReader,
    WorkerRegistry,
)
from atdd.mediate_worker_decisions.sense_decision.src.application.sense_use_case import (
    SenseDecisionUseCase,
)

# domain
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    DecisionRequest,
)

# presentation
from atdd.mediate_worker_decisions.sense_decision.src.presentation import (  # noqa: F401
    emit_cli,
)


def default_id_factory() -> str:
    return str(uuid.uuid4())


def default_clock() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_sense_use_case(
    *,
    reader: SurfaceReader,
    registry: WorkerRegistry,
    sink: RequestSink,
    id_factory: Callable[[], str] = default_id_factory,
    clock: Callable[[], str] = default_clock,
) -> SenseDecisionUseCase:
    return SenseDecisionUseCase(
        reader=reader,
        registry=registry,
        sink=sink,
        id_factory=id_factory,
        clock=clock,
    )


__all__ = [
    "DecisionRequest",
    "SenseDecisionUseCase",
    "build_sense_use_case",
    "default_id_factory",
    "default_clock",
]
