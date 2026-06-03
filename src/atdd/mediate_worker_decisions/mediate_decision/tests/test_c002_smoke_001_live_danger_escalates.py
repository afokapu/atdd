# URN: test:mediate-worker-decisions:mediate-decision:C002-SMOKE-001-live-danger-escalates
# Acceptance: acc:mediate-worker-decisions:C002-SMOKE-001-live-danger-escalates
# WMBT: wmbt:mediate-worker-decisions:C002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C002-SMOKE-001-live-danger-escalates — drive the REAL bridge against a REAL
cmux workspace whose worker offers a dangerous action (git push). The safety
gate must escalate and the coach surface must stay untouched. Runs whenever cmux
is on PATH; skips on runners without cmux.
"""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_c002_smoke_001_live_danger_escalates():
    from atdd.mediate_worker_decisions.live_smoke import danger_escalation_smoke

    evidence = danger_escalation_smoke()
    assert evidence["cause"] == "dangerous_action"
    assert evidence["coach_contacted"] is False
