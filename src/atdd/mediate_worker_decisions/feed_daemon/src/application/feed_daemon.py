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
from typing import List, Optional

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

_LOG = logging.getLogger("atdd.feed_daemon")


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
            outcome = self._runner.handle(item)
            if outcome.escalation is not None:
                # Dangerous / human-required: record durably AND loudly surface
                # it; NEVER auto-answer (WMBT C004 — headline safety property).
                self._escalations.record(outcome.escalation)
                self._log.warning(
                    "ESCALATION REQUIRED — dangerous decision NOT auto-answered: "
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
