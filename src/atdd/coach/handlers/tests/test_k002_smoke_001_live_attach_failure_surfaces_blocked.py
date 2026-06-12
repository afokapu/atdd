# URN: test:mediate-worker-decisions:feed-daemon-durability:K002-SMOKE-001-live-attach-failure-surfaces-blocked
# Acceptance: acc:mediate-worker-decisions:K002-SMOKE-001-live-attach-failure-surfaces-blocked
# WMBT: wmbt:mediate-worker-decisions:K002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""K002-SMOKE-001 — a real dispatch whose attach fails leaves BLOCKED on disk.

Drives a REAL ``atdd coach`` dispatch where the worker daemon attach is induced
to fail, then asserts a durable BLOCKED decision and an escalation record exist
on disk for the unmediated worker.

The harness is real. A real dispatch needs a live cmux multiplexer + spawned
worker process, not inducible in this environment — skipped until run on coach
infrastructure. The BLOCK-on-attach-failure contract is exercised hermetically by
K002-UNIT-001/002.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="requires a live cmux multiplexer + real spawned worker dispatch; "
    "not inducible here — hermetic coverage in K002-UNIT-001/002 (A1)."
)


def test_live_attach_failure_surfaces_blocked(tmp_path):
    from atdd.coach.handlers.live_smoke import attach_failure_blocks_smoke

    evidence = attach_failure_blocks_smoke(tmp_path)
    assert evidence["blocked_recorded"] is True
    assert evidence["escalation_recorded"] is True
    assert evidence["returned_handled"] is False
