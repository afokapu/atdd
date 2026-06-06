# URN: test:mediate-worker-decisions:bridge-cmux-feed:E009-SMOKE-001-worker-actually-proceeds-after-reply
# Acceptance: acc:mediate-worker-decisions:E009-SMOKE-001-worker-actually-proceeds-after-reply
# WMBT: wmbt:mediate-worker-decisions:E009
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E009-SMOKE-001 — a real cmux-native worker actually proceeds after a reply.

The headline #986 proof: drives the REAL production runner (now with the
WorkerAdvance verify→send-key-fallback→re-verify path) against a live cmux-native
worker blocked on an AskUserQuestion, and asserts the worker's screen ACTUALLY
advances past the menu — not merely that the Feed item resolved. Captures a
screen-before/after evidence artifact. Runs whenever cmux is on PATH; skips
otherwise.
"""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_e009_smoke_001_worker_actually_proceeds_after_reply(tmp_path):
    from atdd.mediate_worker_decisions.bridge_cmux_feed.live_smoke import (
        advance_live_smoke,
    )

    evidence = advance_live_smoke(evidence_path=str(tmp_path / "evidence.txt"))

    assert evidence["parked_before"] is True   # really started on the native menu
    assert evidence["advanced"] is True        # worker actually proceeded
