"""Feature composition root for mediate-decision (SPEC-CODER-COMP-0004)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

# application
from atdd.mediate_worker_decisions.mediate_decision.src.application.mediate_use_case import (
    MediateDecisionUseCase,
    build_coach_request,
)
from atdd.mediate_worker_decisions.mediate_decision.src.application.ports import (
    Clock,
    CoachClient,
    EscalationSink,
    VerdictSink,
)

# domain
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (  # noqa: F401
    Escalation,
    Verdict,
)

# integration
from atdd.mediate_worker_decisions.mediate_decision.src.integration.cmux_coach_client import (
    CmuxCoachClient,
    SystemClock,
)
from atdd.mediate_worker_decisions.mediate_decision.src.integration.jsonl_sinks import (
    JsonlEscalationSink,
    JsonlVerdictSink,
)

# presentation
from atdd.mediate_worker_decisions.mediate_decision.src.presentation import (  # noqa: F401
    mediate_cli,
)


def default_id_factory() -> str:
    return str(uuid.uuid4())


def default_clock_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_mediate_use_case(
    *,
    coach: CoachClient,
    clock: Clock,
    verdict_sink: VerdictSink,
    escalation_sink: EscalationSink,
    id_factory: Callable[[], str] = default_id_factory,
    ts_factory: Callable[[], str] = default_clock_text,
    timeout_seconds: float = 180.0,
    poll_interval: float = 2.0,
) -> MediateDecisionUseCase:
    return MediateDecisionUseCase(
        coach=coach,
        clock=clock,
        verdict_sink=verdict_sink,
        escalation_sink=escalation_sink,
        id_factory=id_factory,
        ts_factory=ts_factory,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
        renderer=build_coach_request,
    )


def build_mediate_use_case_from_repo(
    repo_root: Optional[Path] = None,
    coach_surface_id: str = "surface:1",
) -> MediateDecisionUseCase:  # pragma: no cover - exercised by live smoke
    import yaml

    root = Path(repo_root or Path.cwd())
    registry_path = root / ".atdd" / "decision" / "registry.yaml"
    config = yaml.safe_load(registry_path.read_text()) if registry_path.exists() else {}
    config = config or {}
    workspace_id = config.get("workspace_id", "workspace:1")
    coach_surface = (config.get("coach") or {}).get("surface_id", coach_surface_id)
    return build_mediate_use_case(
        coach=CmuxCoachClient(workspace_id, coach_surface),
        clock=SystemClock(),
        verdict_sink=JsonlVerdictSink(root / ".atdd" / "decision" / "verdicts.jsonl"),
        escalation_sink=JsonlEscalationSink(
            root / ".atdd" / "decision" / "escalations.jsonl"
        ),
    )


__all__ = [
    "MediateDecisionUseCase",
    "build_mediate_use_case",
    "build_mediate_use_case_from_repo",
]
