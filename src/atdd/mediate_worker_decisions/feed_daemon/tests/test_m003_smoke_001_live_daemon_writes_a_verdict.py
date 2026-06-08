# URN: test:mediate-worker-decisions:feed-daemon:M003-SMOKE-001-live-daemon-writes-a-verdict
# Acceptance: acc:mediate-worker-decisions:M003-SMOKE-001-live-daemon-writes-a-verdict
# WMBT: wmbt:mediate-worker-decisions:M003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""M003-SMOKE-001 — a live daemon WRITES A VERDICT for a real induced decision.

The headline gate the L007 inclusion smoke missed. Drive the PRODUCTION-wired daemon
(``build_feed_daemon_from_repo`` — real ``CmuxFeedSource`` + ``LlmCoach`` over a real
``claude -p``, real jsonl ledgers) over one poll tick against a live cmux worker blocked
on a real AskUserQuestion, and assert ``verdicts.jsonl`` GAINS A LINE — i.e. the daemon
completed a real decision and recorded it durably, not merely that the scoped source
*includes* the item (the #1007 silent-decide failure). Runs whenever cmux is on PATH;
skips otherwise. Evidence captured per #983.
"""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_m003_smoke_001_live_daemon_writes_a_verdict(tmp_path):
    from atdd.mediate_worker_decisions.feed_daemon.live_smoke import (
        writes_verdict_live_smoke,
    )

    evidence = writes_verdict_live_smoke(tmp_dir=str(tmp_path))

    # The daemon completed a REAL decision and recorded it durably — a written
    # verdict line, not just an item the scope happened to include.
    assert evidence["verdict_written"] is True, (
        "the daemon did not write a verdict for the induced decision — the "
        "silent #1007 decide failure reproduced"
    )
    assert evidence["verdict_lines"] >= 1
    assert evidence["request_id"]
