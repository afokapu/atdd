"""PersistentOrchestrator — the supervisor loop the coach lacks today.

Given a single work item, ``run`` polls the injected ``PhasePoller`` for the
item's current phase and done-signal, and:

  * when the current phase's done-signal is present, drives the injected
    ``PhaseDriver`` to advance to (or re-dispatch for) the next phase — and
    NEVER advances on a poll where the done-signal is absent (WMBT C010);
  * sleeps via the injected clock and repeats until the item reaches a terminal
    phase (COMPLETE/BLOCKED);
  * if a phase never produces its done-signal within the stall threshold of
    consecutive polls, loud-logs a WARNING naming the work item and phase and
    exits the loop rather than hanging mid-transition (WMBT M006).

CORE only: the real cmux runtime is the provider's; this loop touches nothing but
its injected poller, driver, and clock.

Skeleton: behaviour is implemented in GREEN — ``run`` raises here so the RED
acceptances fail behaviourally rather than on import.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from atdd.mediate_worker_decisions.persistent_orchestrator.src.application.ports import (
    PhaseDriver,
    PhasePoller,
    Sleeper,
)
from atdd.mediate_worker_decisions.persistent_orchestrator.src.domain.orchestrator_config import (
    OrchestratorConfig,
)

_LOG = logging.getLogger("atdd.persistent_orchestrator")


@dataclass(frozen=True)
class RunOutcome:
    """The result of one supervised run over a work item."""

    work_item_id: str
    final_phase: str
    stalled: bool
    transitions: int


class PersistentOrchestrator:
    def __init__(
        self,
        *,
        work_item_id: str,
        poller: PhasePoller,
        driver: PhaseDriver,
        sleeper: Sleeper,
        config: Optional[OrchestratorConfig] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._work_item_id = work_item_id
        self._poller = poller
        self._driver = driver
        self._sleeper = sleeper
        self._config = config or OrchestratorConfig()
        self._log = logger or _LOG

    def run(self) -> RunOutcome:
        """Supervise the work item until it reaches a terminal phase or stalls.

        Each pass: poll the current phase/done-signal; stop on a terminal phase;
        advance ONLY when the current phase's done-signal is present (WMBT C010);
        otherwise count a no-progress poll and, once the stall threshold is hit,
        loud-log and exit rather than hang mid-transition (WMBT M006).
        """
        last_phase: Optional[str] = None
        polls_without_progress = 0
        transitions = 0

        while True:
            snap = self._poller.poll(self._work_item_id)

            if self._config.is_terminal(snap.phase):
                self._log.info(
                    "work-item %s reached terminal phase %s after %d transition(s)",
                    self._work_item_id,
                    snap.phase,
                    transitions,
                )
                return RunOutcome(
                    work_item_id=self._work_item_id,
                    final_phase=snap.phase,
                    stalled=False,
                    transitions=transitions,
                )

            # A phase change is progress: reset the stall counter for the new phase.
            if snap.phase != last_phase:
                last_phase = snap.phase
                polls_without_progress = 0

            if snap.done_signal:
                # The done-signal IS present — and only here do we advance (C010).
                self._driver.advance(self._work_item_id, snap.phase)
                transitions += 1
                polls_without_progress = 0
            else:
                polls_without_progress += 1
                if polls_without_progress >= self._config.stall_threshold:
                    # Stuck mid-phase: surface it loudly and exit (M006) — the
                    # fire-and-forget coach used to hang here in silence.
                    self._log.warning(
                        "STALL — work-item %s stuck in phase %s for %d poll(s) "
                        "without a done-signal; surfacing and exiting",
                        self._work_item_id,
                        snap.phase,
                        polls_without_progress,
                    )
                    return RunOutcome(
                        work_item_id=self._work_item_id,
                        final_phase=snap.phase,
                        stalled=True,
                        transitions=transitions,
                    )

            self._sleeper.sleep(self._config.poll_interval_s)
