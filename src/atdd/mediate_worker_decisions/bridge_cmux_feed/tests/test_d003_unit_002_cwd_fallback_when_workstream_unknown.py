# URN: test:mediate-worker-decisions:bridge-cmux-feed:D003-UNIT-002-cwd-fallback-when-workstream-unknown
# Acceptance: acc:mediate-worker-decisions:D003-UNIT-002-cwd-fallback-when-workstream-unknown
# WMBT: wmbt:mediate-worker-decisions:D003
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""D003-UNIT-002 — cwd is the fallback when an item's workstream is unknown.

The precise signal is ``workstream_id`` (the claude session). When an item
carries no resolvable ``workstream_id`` the scope falls back to the workspace's
worktree ``cwd`` — a real spawned worker runs in a unique worktree, so cwd
isolates distinct workers. An item whose cwd belongs to a SIBLING worktree is
still excluded.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.workspace_scope import (
    WorkspaceScope,
)


def _item(request_id: str, workstream_id, cwd: str) -> FeedItem:
    return FeedItem(
        id=request_id,
        request_id=request_id,
        kind="question",
        workstream_id=workstream_id,
        cwd=cwd,
    )


def test_cwd_fallback_keeps_own_cwd_excludes_sibling_worktree():
    scope = WorkspaceScope(
        workstream_ids=frozenset({"claude-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}),
        cwds=frozenset({"/tmp/wt-a"}),
    )

    no_workstream_my_cwd = _item("req-fallback", None, "/tmp/wt-a")
    sibling_worktree = _item("req-sibling", None, "/tmp/wt-b")

    kept = scope.filter([no_workstream_my_cwd, sibling_worktree])

    # workstream-less item in our worktree is kept via the cwd fallback
    assert [i.request_id for i in kept] == ["req-fallback"]
    # a sibling worktree's item is excluded even with no workstream signal
    assert all(i.cwd != "/tmp/wt-b" for i in kept)
