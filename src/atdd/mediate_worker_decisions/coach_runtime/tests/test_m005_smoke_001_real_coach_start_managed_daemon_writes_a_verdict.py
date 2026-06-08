# URN: test:mediate-worker-decisions:coach-runtime:M005-SMOKE-001-real-coach-start-managed-daemon-writes-a-verdict
# Acceptance: acc:mediate-worker-decisions:M005-SMOKE-001-real-coach-start-managed-daemon-writes-a-verdict
# WMBT: wmbt:mediate-worker-decisions:M005
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""M005-SMOKE-001 — the REAL `atdd coach start` managed daemon writes a verdict.

The headline gate every prior #1007 round missed. M003-SMOKE drove the daemon LOOP
directly (``build_feed_daemon`` + ``tick``) and PASSED while the real command was
broken — because the bug is in the detached spawn, not the loop: ``atdd coach start``
launches the daemon via ``SubprocessDaemonSpawner`` and the detached child inherited
the coach session's stale ``CMUX_*`` client-context env, so its ``cmux rpc`` broke-pipe
and ``run_cmux`` swallowed it into an empty Feed.

This drives the PRODUCTION entry point (``CoachRuntime.start`` over the real
``SubprocessDaemonSpawner`` — the same call ``atdd coach start --workspace <ws>``
makes) against a live worker blocked on a real AskUserQuestion, and asserts the
MANAGED daemon's own ``verdicts.jsonl`` GAINS A LINE. Runs whenever cmux is on PATH;
skips otherwise. Evidence captured (#983).
"""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_m005_smoke_001_real_coach_start_managed_daemon_writes_a_verdict(tmp_path):
    from atdd.mediate_worker_decisions.coach_runtime.live_smoke import (
        real_coach_start_writes_verdict_live_smoke,
    )

    evidence = real_coach_start_writes_verdict_live_smoke(tmp_dir=str(tmp_path))

    if evidence.get("skipped"):
        pytest.skip(evidence.get("reason", "live substrate unavailable"))

    # The daemon spawned by the REAL command reached cmux cleanly, decided the
    # blocked question, and recorded a verdict to its managed ledger — proving the
    # production entry point decides, not merely the loop in isolation.
    assert evidence["verdict_written"] is True, (
        "the managed daemon started by `atdd coach start` wrote no verdict — the "
        "stale-CMUX-env broken-pipe #1007 reopen reproduced. daemon.log tail:\n"
        + evidence.get("daemon_log_tail", "")
    )
    assert evidence["verdict_lines"] >= 1
    assert evidence["request_id"]
