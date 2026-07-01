# URN: test:mediate-worker-decisions:persistent-orchestrator:C010-UNIT-001-advances-only-on-done-signal
# Acceptance: acc:mediate-worker-decisions:C010-UNIT-001-advances-only-on-done-signal
# WMBT: wmbt:mediate-worker-decisions:C010
# Phase: RED
# Layer: application
# Assertion: behavioral
"""C010-UNIT-001 — the supervisor advances only on the phase done-signal.

Over a scripted PLANNED->RED->GREEN->COMPLETE run that alternates done-signal
absent then present before each transition, the supervisor drives the phase
driver exactly once per done-signal (three transitions, in phase order) and
never on a poll where the current phase's done-signal is absent, stopping at the
terminal phase COMPLETE.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.persistent_orchestrator.src.domain.phase_snapshot import (
    PhaseSnapshot,
)
from atdd.mediate_worker_decisions.persistent_orchestrator.tests._helpers import (
    make_orchestrator,
)


def test_advances_only_on_done_signal():
    # done-signal absent, then present, before each of three transitions.
    snapshots = [
        PhaseSnapshot("PLANNED", done_signal=False),
        PhaseSnapshot("PLANNED", done_signal=True),
        PhaseSnapshot("RED", done_signal=False),
        PhaseSnapshot("RED", done_signal=True),
        PhaseSnapshot("GREEN", done_signal=False),
        PhaseSnapshot("GREEN", done_signal=True),
        PhaseSnapshot("COMPLETE", done_signal=False),
    ]
    orch, _poller, driver, _sleeper = make_orchestrator(snapshots=snapshots)

    outcome = orch.run()

    # advanced exactly once per phase that reported its done-signal, in order.
    assert [from_phase for _wid, from_phase in driver.calls] == ["PLANNED", "RED", "GREEN"]
    # never advanced more than the three done-signals (no early/extra advance).
    assert len(driver.calls) == 3
    assert outcome.transitions == 3
    assert outcome.final_phase == "COMPLETE"
    assert outcome.stalled is False
