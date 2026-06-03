# URN: test:mediate-worker-decisions:bridge-cmux-feed:C003-SMOKE-001-live-dangerous-not-auto-approved
# Acceptance: acc:mediate-worker-decisions:C003-SMOKE-001-live-dangerous-not-auto-approved
# WMBT: wmbt:mediate-worker-decisions:C003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C003-SMOKE-001 — a real agent's dangerous tool use is not auto-approved.

Drives the REAL bridge against a live cmux workspace whose blocked permission
requests a dangerous command: no auto reply is sent and the item is escalated
for human review. Runs whenever cmux is on PATH; skips on runners without cmux.
"""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_c003_smoke_001_live_dangerous_not_auto_approved():
    from atdd.mediate_worker_decisions.bridge_cmux_feed.live_smoke import (
        PermissionNotInducible,
        danger_live_smoke,
    )

    try:
        evidence = danger_live_smoke()
    except PermissionNotInducible:
        pytest.skip(
            "no blocked dangerous permission inducible under cmux auto-mode "
            "(--allow-dangerously-skip-permissions); unit+integration carry the "
            "C003 guarantee"
        )
    assert evidence["cause"] == "dangerous_action"
    assert evidence["auto_replied"] is False
