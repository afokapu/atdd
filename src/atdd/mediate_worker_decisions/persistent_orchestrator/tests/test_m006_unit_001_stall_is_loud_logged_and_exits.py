# URN: test:mediate-worker-decisions:persistent-orchestrator:M006-UNIT-001-stall-is-loud-logged-and-exits
# Acceptance: acc:mediate-worker-decisions:M006-UNIT-001-stall-is-loud-logged-and-exits
# WMBT: wmbt:mediate-worker-decisions:M006
# Phase: RED
# Layer: application
# Assertion: behavioral
"""M006-UNIT-001 — a stall is loud-logged and exits the loop.

When the current phase never produces its done-signal, after the stall threshold
of consecutive polls the supervisor emits a WARNING-or-higher record naming the
work item and the stuck phase, returns a stalled outcome (rather than looping
forever), and never advances the phase driver.
"""
from __future__ import annotations

import logging

from atdd.mediate_worker_decisions.persistent_orchestrator.src.domain.orchestrator_config import (
    OrchestratorConfig,
)
from atdd.mediate_worker_decisions.persistent_orchestrator.src.domain.phase_snapshot import (
    PhaseSnapshot,
)
from atdd.mediate_worker_decisions.persistent_orchestrator.tests._helpers import (
    capturing_logger,
    make_orchestrator,
)


def test_stall_is_loud_logged_and_exits():
    logger, records = capturing_logger()
    # The work item is stuck: same non-terminal phase, done-signal never appears.
    snapshots = [PhaseSnapshot("RED", done_signal=False)]
    config = OrchestratorConfig(stall_threshold=3)
    orch, _poller, driver, _sleeper = make_orchestrator(
        snapshots=snapshots, config=config, logger=logger, work_item_id="1082"
    )

    outcome = orch.run()

    # surfaced loudly: a WARNING+ record naming the work item and the stuck phase.
    warnings = [r for r in records if r.levelno >= logging.WARNING]
    assert warnings, "a stall must be surfaced with a WARNING-or-higher record"
    msg = warnings[0].getMessage()
    assert "1082" in msg and "RED" in msg
    # exited rather than hanging, and never advanced the phase.
    assert outcome.stalled is True
    assert outcome.final_phase == "RED"
    assert driver.calls == []
