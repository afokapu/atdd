# URN: test:mediate-worker-decisions:bridge-cmux-feed:L007-SMOKE-001-live-worktree-worker-decision-not-swallowed
# Acceptance: acc:mediate-worker-decisions:L007-SMOKE-001-live-worktree-worker-decision-not-swallowed
# WMBT: wmbt:mediate-worker-decisions:L007
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""L007-SMOKE-001 — a live worktree worker's decision is NOT scoped out (#993/#1004).

The headline #1004 proof. Spawn a REAL cmux-native claude worker launched at a repo
root (the surface's launch cwd) that ``cd``s into a flat-sibling git worktree and blocks
on a live AskUserQuestion — exactly how the coach runs real workers, the configuration
the #993 workspace scope silently swallowed. Build a workspace-scoped ``CmuxFeedSource``
for that workspace and assert it INCLUDES the worker's pending decision (so the daemon
would decide or escalate it). Captures the matched worktree cwd / workstream as evidence
(#983). Runs whenever cmux is on PATH; skips otherwise.
"""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_l007_smoke_001_live_worktree_worker_decision_not_swallowed(tmp_path):
    from atdd.mediate_worker_decisions.bridge_cmux_feed.live_smoke import (
        worktree_scope_live_smoke,
    )

    evidence = worktree_scope_live_smoke(evidence_path=str(tmp_path / "evidence.txt"))

    # the worktree-launched worker's surface launch cwd and its real (worktree) cwd
    # genuinely differ — this is the #1004 regression configuration
    assert evidence["launch_cwd"] != evidence["worktree_cwd"], (
        "launch cwd and worktree cwd were the same — the regression was not reproduced"
    )
    # the workspace-scoped source INCLUDED the worktree worker's decision rather
    # than silently scoping it out (the #993 bug)
    assert evidence["scoped_request_id"], (
        "the workspace-scoped source saw no decision — the worktree worker's "
        "decision was scoped out (the #1004 regression)"
    )
    assert evidence["scoped_request_id"] in evidence["scoped_seen_request_ids"]
