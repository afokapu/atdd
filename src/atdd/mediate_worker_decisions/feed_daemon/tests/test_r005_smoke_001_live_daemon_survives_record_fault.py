# URN: test:mediate-worker-decisions:feed-daemon-durability:R005-SMOKE-001-live-daemon-survives-record-fault
# Acceptance: acc:mediate-worker-decisions:R005-SMOKE-001-live-daemon-survives-record-fault
# WMBT: wmbt:mediate-worker-decisions:R005
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""R005-SMOKE-001 — a live daemon whose verdict ledger is unwritable keeps polling.

Drives the REAL daemon process against a live Feed with its verdict-ledger path
forced read-only; when a blocked item is answered the verdict write fails, and
the daemon must escalate-and-continue rather than crash.

The harness is real. The live condition needs a real spawned worker whose prompt
reaches the cmux Feed (blocked by #967) plus a long-running daemon process, which
is not inducible in this environment — skipped until the live Feed wiring lands.
The survival behaviour is exercised hermetically by R005-UNIT-001/002.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="requires a live spawned worker on the cmux Feed (#967) plus a "
    "long-running daemon process; not inducible here — hermetic coverage in "
    "R005-UNIT-001/002 (C2)."
)


def test_live_daemon_survives_record_fault():
    from atdd.mediate_worker_decisions.feed_daemon.live_smoke import (
        daemon_survives_record_fault_smoke,
    )

    evidence = daemon_survives_record_fault_smoke()
    assert evidence["daemon_alive"] is True
    assert evidence["escalated"] is True
