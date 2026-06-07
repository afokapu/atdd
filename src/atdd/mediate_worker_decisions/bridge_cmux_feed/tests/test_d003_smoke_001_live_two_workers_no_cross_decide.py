# URN: test:mediate-worker-decisions:bridge-cmux-feed:D003-SMOKE-001-live-two-workers-no-cross-decide
# Acceptance: acc:mediate-worker-decisions:D003-SMOKE-001-live-two-workers-no-cross-decide
# WMBT: wmbt:mediate-worker-decisions:D003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""D003-SMOKE-001 — two live workers, each scoped consumer sees only its own.

The headline #993 proof: spawn TWO real cmux-native workers in TWO workspaces,
each blocked on a DISTINCT live AskUserQuestion. Build a workspace-scoped
``CmuxFeedSource`` for each and assert each sees ONLY its own worker's pending
decision — no cross-decide, and no duplicate ``request_id`` across the two scoped
result sets (the two-daemon bug). Captures evidence (#983). Runs whenever cmux is
on PATH; skips otherwise.
"""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_d003_smoke_001_live_two_workers_no_cross_decide(tmp_path):
    from atdd.mediate_worker_decisions.bridge_cmux_feed.live_smoke import (
        scope_isolation_live_smoke,
    )

    evidence = scope_isolation_live_smoke(
        evidence_path=str(tmp_path / "evidence.txt")
    )

    # each scoped consumer located its own worker's distinct decision
    assert evidence["a_request_id"], "workspace A scoped source saw no decision"
    assert evidence["b_request_id"], "workspace B scoped source saw no decision"
    # the two are genuinely distinct decisions
    assert evidence["a_request_id"] != evidence["b_request_id"]
    # no cross-decide: neither scoped source saw the other worker's request_id
    assert evidence["a_request_id"] not in evidence["b_seen_request_ids"]
    assert evidence["b_request_id"] not in evidence["a_seen_request_ids"]
    # the two scoped result sets share no request_id (the two-daemon bug is gone)
    assert evidence["shared_request_ids"] == []
