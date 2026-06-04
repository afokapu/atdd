# URN: test:mediate-worker-decisions:surface-worker-decisions:C006-SMOKE-001-live-bash-decision-surfaces-not-auto-executed
# Acceptance: acc:mediate-worker-decisions:C006-SMOKE-001-live-bash-decision-surfaces-not-auto-executed
# WMBT: wmbt:mediate-worker-decisions:C006
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C006-SMOKE-001 — a worker's Bash command surfaces instead of auto-executing.

Live end-to-end: a toolkit-spawned worker asked to run a Bash command produces a
pending kind=permission item in feed.list (command verbatim in tool_input) rather
than executing it. The harness is real; runs at the SMOKE phase after GREEN.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="requires spawn-agents leash retirement + adapter wiring (#NEW); #967 "
    "lands the producer feature hermetic-only — goes live when that issue lands"
)


def test_c005_smoke_001_live_bash_decision_surfaces_not_auto_executed():
    from atdd.mediate_worker_decisions.surface_worker_decisions.live_smoke import (
        bash_decision_surfaces_live_smoke,
    )

    evidence = bash_decision_surfaces_live_smoke()
    assert evidence["surfaced"] is True
