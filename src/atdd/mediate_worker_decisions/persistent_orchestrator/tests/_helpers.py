"""Hermetic fakes for the persistent-orchestrator acceptances.

A scripted phase poller (returns a fixed sequence of snapshots, then holds on the
last), a recording phase driver, a no-op sleeper (so the loop is instant), and a
capturing logger. No real clock and no real cmux — the loop is pure CORE.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from atdd.mediate_worker_decisions.persistent_orchestrator.src.application.persistent_orchestrator import (
    PersistentOrchestrator,
)
from atdd.mediate_worker_decisions.persistent_orchestrator.src.domain.orchestrator_config import (
    OrchestratorConfig,
)
from atdd.mediate_worker_decisions.persistent_orchestrator.src.domain.phase_snapshot import (
    PhaseSnapshot,
)


class ScriptedPoller:
    """Yields a fixed sequence of snapshots, repeating the last one forever."""

    def __init__(self, snapshots: List[PhaseSnapshot]) -> None:
        assert snapshots, "ScriptedPoller needs at least one snapshot"
        self._snapshots = snapshots
        self.polls = 0

    def poll(self, work_item_id: str) -> PhaseSnapshot:
        idx = min(self.polls, len(self._snapshots) - 1)
        self.polls += 1
        return self._snapshots[idx]


class RecordingDriver:
    """Records each (work_item_id, from_phase) advance the supervisor drives."""

    def __init__(self) -> None:
        self.calls: List[Tuple[str, str]] = []

    def advance(self, work_item_id: str, from_phase: str) -> None:
        self.calls.append((work_item_id, from_phase))


class NoopSleeper:
    """Pacing seam wired to nothing — the loop never actually waits."""

    def __init__(self) -> None:
        self.sleeps: List[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: List[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def capturing_logger(name: str = "atdd.persistent_orchestrator.test") -> Tuple[logging.Logger, List[logging.LogRecord]]:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers = []
    handler = _ListHandler()
    logger.addHandler(handler)
    logger.propagate = False
    return logger, handler.records


def make_orchestrator(
    *,
    snapshots: List[PhaseSnapshot],
    config: Optional[OrchestratorConfig] = None,
    logger: Optional[logging.Logger] = None,
    work_item_id: str = "1082",
) -> Tuple[PersistentOrchestrator, ScriptedPoller, RecordingDriver, NoopSleeper]:
    poller = ScriptedPoller(snapshots)
    driver = RecordingDriver()
    sleeper = NoopSleeper()
    orch = PersistentOrchestrator(
        work_item_id=work_item_id,
        poller=poller,
        driver=driver,
        sleeper=sleeper,
        config=config or OrchestratorConfig(),
        logger=logger,
    )
    return orch, poller, driver, sleeper
