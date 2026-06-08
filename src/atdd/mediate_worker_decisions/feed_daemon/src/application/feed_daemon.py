"""FeedDaemonUseCase — the continuous loop around the bridge decide/escalate brain.

Per tick: poll the Feed, skip request_ids already answered (idempotency, WMBT
E005), and for each fresh blocked item drive the production ``FeedRunnerUseCase``
(reused wholesale — no decide/escalate logic is duplicated here). A verdict is
delivered by the runner and recorded to the durable verdict ledger; an escalation
is recorded to the escalation sink AND loudly logged, and NO reply is delivered
(WMBT C004 — the headline safety property). ``run_forever`` runs the loop under a
single-instance lock (WMBT D002) until the stop signal fires (WMBT R002).

Skeleton: behaviour is implemented in GREEN; the loop body raises here so the RED
acceptances fail behaviourally rather than on import.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, List, Optional

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.application.feed_runner import (
    FeedOutcome,
    FeedRunnerUseCase,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.application.ports import FeedSource
from atdd.mediate_worker_decisions.feed_daemon.src.application.ports import (
    EscalationSink,
    Lock,
    Sleeper,
    StopSignal,
    VerdictLedger,
)
from atdd.mediate_worker_decisions.feed_daemon.src.domain.answered_set import AnsweredSet
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    CAUSE_DECIDE_FAILED,
    Escalation,
)

_LOG = logging.getLogger("atdd.feed_daemon")


def _default_id() -> str:
    return str(uuid.uuid4())


def _default_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


class SingleInstanceError(RuntimeError):
    """Raised when run_forever cannot acquire the single-instance lock."""


class FeedDaemonUseCase:
    def __init__(
        self,
        *,
        source: FeedSource,
        runner: FeedRunnerUseCase,
        answered: AnsweredSet,
        escalation_sink: EscalationSink,
        verdict_ledger: VerdictLedger,
        sleeper: Sleeper,
        stop: StopSignal,
        lock: Lock,
        poll_interval_s: float = 2.0,
        logger: Optional[logging.Logger] = None,
        id_factory: Callable[[], str] = _default_id,
        ts_factory: Callable[[], str] = _default_ts,
    ) -> None:
        self._source = source
        self._runner = runner
        self._answered = answered
        self._escalations = escalation_sink
        self._verdicts = verdict_ledger
        self._sleeper = sleeper
        self._stop = stop
        self._lock = lock
        self._interval = poll_interval_s
        self._log = logger or _LOG
        # Factories for the decide-failure escalation the loop raises itself (the
        # runner owns its own for the decisions it escalates).
        self._id = id_factory
        self._ts = ts_factory

    def tick(self) -> List[FeedOutcome]:
        """One poll pass: handle each fresh blocked item exactly once.

        Idempotency is enforced HERE, before ``runner.handle`` — a request_id in
        the answered-set is skipped so the coach is never re-paid and a still-
        blocked dangerous item is not re-escalated every poll (WMBT E005).
        """
        outcomes: List[FeedOutcome] = []
        for item in self._source.list_pending():
            if self._answered.seen(item.request_id):
                continue
            try:
                outcome = self._runner.handle(item)
            except Exception:
                outcome = self._on_decide_failure(item)
            if outcome.escalation is not None:
                # Dangerous / human-required: record durably AND loudly surface
                # it; NEVER auto-answer (WMBT C004 — headline safety property).
                self._escalations.record(outcome.escalation)
                # Covers both causes that reach here: a dangerous decision never
                # auto-answered (WMBT C004) and a worker that stayed parked even
                # after the send-key fallback (worker_stuck, #986) — the reply was
                # never silently claimed as delivered.
                self._log.warning(
                    "ESCALATION REQUIRED — decision NOT auto-resolved: "
                    "request_id=%s cause=%s (a human must review)",
                    outcome.escalation.request_id,
                    outcome.escalation.cause,
                )
            elif outcome.verdict is not None:
                # Auto-answered: the runner already delivered the reply; record
                # the verdict durably for audit + restart re-hydration.
                self._verdicts.record(outcome.verdict)
            self._answered.mark(item.request_id)
            outcomes.append(outcome)
        return outcomes

    def _on_decide_failure(self, item) -> FeedOutcome:
        """Turn a raised decide failure into an observable escalation (#1007).

        The decide path failed for this item (e.g. the LlmCoach ``claude -p`` call
        died in the detached, no-TTY daemon context). NEVER swallow it into zero
        verdicts / zero escalations: loud-log with the traceback AND raise a
        human-required escalation so the failure leaves a durable trace, then let
        the caller keep polling rather than crash the whole daemon.
        """
        self._log.exception(
            "DECIDE LOOP FAILED — request_id=%s could not be auto-resolved in the "
            "daemon; escalating to a human and continuing",
            item.request_id,
        )
        return FeedOutcome(
            request_id=item.request_id,
            escalation=Escalation(
                escalation_id=self._id(),
                request_id=item.request_id,
                raised_at=self._ts(),
                cause=CAUSE_DECIDE_FAILED,
                safety_class=None,
            ),
        )

    def run_forever(self) -> None:
        """Loop tick()+sleep under the single-instance lock until stop fires.

        The single-instance guard (WMBT D002) is acquired up front: if another
        daemon holds it, we refuse to start rather than answer the same Feed
        twice. The lock is released in a finally so a SIGINT/SIGTERM-driven stop
        (WMBT R002) never leaves it wedged.
        """
        if not self._lock.acquire():
            raise SingleInstanceError(
                "another feed daemon already holds the single-instance lock"
            )
        try:
            while not self._stop.is_set():
                self.tick()
                self._sleeper.sleep(self._interval)
        finally:
            self._lock.release()
