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

from atdd.mediate_worker_decisions.surface_worker_decisions.live_smoke import (
    bash_decision_surfaces_live_smoke,
    live_smoke_available,
)


def test_c006_smoke_001_live_bash_decision_surfaces_not_auto_executed():
    # Live-on-demand: spawns a real worker under cmux. Skips cleanly in CI / when
    # not opted in (ATDD_LIVE_SMOKE=1). Documented run: docs/smoke-audit.md (#971).
    skip = live_smoke_available()
    if skip:
        pytest.skip(skip)
    evidence = bash_decision_surfaces_live_smoke()
    assert evidence["surfaced"] is True
    assert evidence["evidence"]["kind"] == "permissionRequest"
    assert evidence["evidence"]["tool_name"] == "Bash"
