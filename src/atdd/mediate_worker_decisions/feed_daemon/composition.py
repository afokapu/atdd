"""Feature composition root for feed-daemon.

``build_feed_daemon`` wires the use case from already-built collaborators (used
by tests). ``build_feed_daemon_from_repo`` is the production wiring: it reuses
bridge-cmux-feed's ``build_feed_runner`` (decide/escalate) WHOLESALE behind a
single shared ``CmuxFeedSource``, and adds the daemon-only adapters — jsonl
ledgers, a pidfile lock, signal-driven stop, and a real sleeper — plus an
answered-set re-hydrated from the durable ledgers (idempotent across restart).
"""
from __future__ import annotations

from typing import Optional

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.application.feed_runner import (
    FeedRunnerUseCase,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.application.ports import FeedSource
from atdd.mediate_worker_decisions.feed_daemon.src.application.feed_daemon import (
    FeedDaemonUseCase,
)
from atdd.mediate_worker_decisions.feed_daemon.src.application.ports import (
    EscalationSink,
    Lock,
    Sleeper,
    StopSignal,
    VerdictLedger,
)
from atdd.mediate_worker_decisions.feed_daemon.src.domain.answered_set import AnsweredSet
from atdd.mediate_worker_decisions.feed_daemon.src.domain.daemon_config import DaemonConfig


def build_feed_daemon(
    *,
    source: FeedSource,
    runner: FeedRunnerUseCase,
    escalation_sink: EscalationSink,
    verdict_ledger: VerdictLedger,
    sleeper: Sleeper,
    stop: StopSignal,
    lock: Lock,
    answered: Optional[AnsweredSet] = None,
    poll_interval_s: float = 2.0,
) -> FeedDaemonUseCase:
    """Wire the daemon from explicit collaborators (test + production seam)."""
    return FeedDaemonUseCase(
        source=source,
        runner=runner,
        answered=answered or AnsweredSet(),
        escalation_sink=escalation_sink,
        verdict_ledger=verdict_ledger,
        sleeper=sleeper,
        stop=stop,
        lock=lock,
        poll_interval_s=poll_interval_s,
    )


def build_feed_daemon_from_repo(*, config: DaemonConfig) -> FeedDaemonUseCase:  # pragma: no cover - live
    """Production wiring: reuse build_feed_runner wholesale behind a shared source."""
    from atdd.mediate_worker_decisions.bridge_cmux_feed.composition import build_feed_runner
    from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.llm_coach import (
        LlmCoach,
    )
    from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_event_source import (
        CmuxFeedSource,
    )
    from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_reply_applier import (
        CmuxFeedTransport,
    )
    from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_advance_verifier import (
        CmuxWorkerAdvance,
    )
    from atdd.mediate_worker_decisions.feed_daemon.src.integration.jsonl_ledgers import (
        JsonlEscalationSink,
        JsonlVerdictLedger,
        read_handled_request_ids,
    )
    from atdd.mediate_worker_decisions.feed_daemon.src.integration.pidfile_lock import (
        PidfileLock,
    )
    from atdd.mediate_worker_decisions.feed_daemon.src.integration.signal_stop import (
        RealSleeper,
        SignalStop,
    )

    source = CmuxFeedSource()  # one shared source for poll + runner
    runner = build_feed_runner(
        source=source,
        reply=CmuxFeedTransport(),
        coach=LlmCoach(provider=config.coach_provider, model=config.coach_model),
        # #981 policy knob: default ESCALATE keeps the C004 human-in-the-loop
        # contract (the live daemon never auto-answers a dangerous action). An
        # operator running fully unattended sets ``dangerous_permission_policy:
        # deny`` so a dangerous tool-use is blocked immediately instead of
        # stalling the worker at the 120s soft-wait.
        dangerous_permission_policy=config.dangerous_permission_policy,
        # #986: verify the worker actually advanced after each auto-verdict and
        # send-key the pre-highlighted selection if the Feed reply lost the race;
        # escalate worker_stuck rather than silently claim delivered.
        advance=CmuxWorkerAdvance(workspace_id=config.workspace_id),
    )
    answered = AnsweredSet(
        read_handled_request_ids(config.verdicts_path, config.escalations_path)
    )
    return build_feed_daemon(
        source=source,
        runner=runner,
        escalation_sink=JsonlEscalationSink(config.escalations_path),
        verdict_ledger=JsonlVerdictLedger(config.verdicts_path),
        sleeper=RealSleeper(),
        stop=SignalStop().install(),
        lock=PidfileLock(config.lock_path),
        answered=answered,
        poll_interval_s=config.poll_interval_s,
    )


__all__ = ["build_feed_daemon", "build_feed_daemon_from_repo"]
