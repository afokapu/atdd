# URN: test:mediate-worker-decisions:feed-daemon-durability:K003-SMOKE-001-live-coach-escalation-persists
# Acceptance: acc:mediate-worker-decisions:K003-SMOKE-001-live-coach-escalation-persists
# WMBT: wmbt:mediate-worker-decisions:K003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""K003-SMOKE-001 — a coach-side escalation raised in a real run persists on disk.

Drives a REAL coach run that triggers a coach-side ``_escalate`` and asserts a
durable escalation record for that reason survives on disk after the run — an
operator finds it after stderr has scrolled away.

The harness is real. A real coach run needs a live dispatch loop, not inducible
in this environment — skipped until run on coach infrastructure. The durable-sink
contract is exercised hermetically by K003-UNIT-001/002.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="requires a live coach run loop to raise a real coach-side "
    "escalation; not inducible here — hermetic coverage in K003-UNIT-001/002 (A0)."
)


def test_live_coach_escalation_persists(tmp_path):
    from atdd.coach.handlers.live_smoke import coach_escalation_persists_smoke

    evidence = coach_escalation_persists_smoke(tmp_path)
    assert evidence["escalation_on_disk"] is True
