"""Feature composition root for sense-decision (SPEC-CODER-COMP-0004).

Wires the four tiers — domain (via the use case), application, integration
adapters, presentation entrypoints — and is the only place allowed to construct
the concrete cmux/persistence dependencies.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

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

# integration
from atdd.mediate_worker_decisions.sense_decision.src.integration.cmux_surface_reader import (
    CmuxSurfaceReader,
)
from atdd.mediate_worker_decisions.sense_decision.src.integration.jsonl_request_sink import (
    JsonlRequestSink,
)
from atdd.mediate_worker_decisions.sense_decision.src.integration.registry_worker_lookup import (
    RegistryWorkerLookup,
)

# presentation
from atdd.mediate_worker_decisions.sense_decision.src.presentation import (  # noqa: F401
    emit_cli,
    notify_hook,
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


def build_sense_use_case_from_repo(
    repo_root: Optional[Path] = None,
) -> SenseDecisionUseCase:  # pragma: no cover - exercised by live smoke
    """Production wiring from ``.atdd/decision/`` config + the cmux backend."""
    import yaml
    from atdd.coach.utils.multiplexer import CmuxBackend

    root = Path(repo_root or Path.cwd())
    registry_path = root / ".atdd" / "decision" / "registry.yaml"
    config = {}
    if registry_path.exists():
        config = yaml.safe_load(registry_path.read_text()) or {}

    reader = CmuxSurfaceReader(CmuxBackend())
    registry = RegistryWorkerLookup.from_config(config)
    sink = JsonlRequestSink(root / ".atdd" / "decision" / "requests.jsonl")
    return build_sense_use_case(reader=reader, registry=registry, sink=sink)


__all__ = [
    "DecisionRequest",
    "SenseDecisionUseCase",
    "build_sense_use_case",
    "build_sense_use_case_from_repo",
    "default_id_factory",
    "default_clock",
]
