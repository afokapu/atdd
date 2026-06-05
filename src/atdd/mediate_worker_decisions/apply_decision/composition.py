"""Feature composition root for apply-decision (SPEC-CODER-COMP-0004)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

# application
from atdd.mediate_worker_decisions.apply_decision.src.application.apply_use_case import (
    ApplyDecisionUseCase,
)
from atdd.mediate_worker_decisions.apply_decision.src.application.ports import (
    AppliedGuard,
    DecisionLedger,
    WorkerApplier,
)

# domain
from atdd.mediate_worker_decisions.apply_decision.src.domain.record import (  # noqa: F401
    DecisionRecord,
)

# integration
from atdd.mediate_worker_decisions.apply_decision.src.integration.agent_control_applier import (
    AgentControlApplier,
    InMemoryAppliedGuard,
)
from atdd.mediate_worker_decisions.apply_decision.src.integration.jsonl_decision_ledger import (
    JsonlDecisionLedger,
)

# presentation
from atdd.mediate_worker_decisions.apply_decision.src.presentation import (  # noqa: F401
    apply_cli,
)


def default_id_factory() -> str:
    return str(uuid.uuid4())


def default_clock_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_apply_use_case(
    *,
    applier: WorkerApplier,
    ledger: DecisionLedger,
    guard: AppliedGuard,
    id_factory: Callable[[], str] = default_id_factory,
    ts_factory: Callable[[], str] = default_clock_text,
) -> ApplyDecisionUseCase:
    return ApplyDecisionUseCase(
        applier=applier,
        ledger=ledger,
        guard=guard,
        id_factory=id_factory,
        ts_factory=ts_factory,
    )


def build_apply_use_case_from_repo(
    repo_root: Optional[Path] = None,
) -> ApplyDecisionUseCase:  # pragma: no cover - exercised by live smoke
    from atdd.runtime.agent_control import CmuxAgentController

    root = Path(repo_root or Path.cwd())
    return build_apply_use_case(
        applier=AgentControlApplier(CmuxAgentController()),
        ledger=JsonlDecisionLedger(root / ".atdd" / "decision" / "decisions.jsonl"),
        guard=InMemoryAppliedGuard(),
    )


__all__ = [
    "ApplyDecisionUseCase",
    "build_apply_use_case",
    "build_apply_use_case_from_repo",
]
