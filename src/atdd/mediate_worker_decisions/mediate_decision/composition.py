"""Feature composition root for mediate-decision (SPEC-CODER-COMP-0004).

The production screen-scrape wiring (``build_mediate_use_case_from_repo`` over
``CmuxCoachClient`` / ``SystemClock`` / JSONL sinks) was removed in 3.90.0; the
cmux Feed integration (``atdd.mediate_worker_decisions.bridge_cmux_feed``, which
uses ``ClaudeCoach``) is the channel now. ``build_mediate_use_case`` remains for
dependency-injected wiring (the coach + clock + sinks are supplied by callers).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

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


__all__ = [
    "MediateDecisionUseCase",
    "build_mediate_use_case",
]
