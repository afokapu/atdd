# URN: test:mediate-worker-decisions:bridge-cmux-feed:L005-UNIT-001-scope-returns-only-own-workspace-items
# Acceptance: acc:mediate-worker-decisions:L005-UNIT-001-scope-returns-only-own-workspace-items
# WMBT: wmbt:mediate-worker-decisions:L005
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""L005-UNIT-001 — the scope keeps only the configured workspace's items.

A per-workspace daemon must not act on another workspace's decisions. Given a
mixed list of feed items carrying different ``workstream_id``s, a
``WorkspaceScope`` built from the configured workspace's workstream identity
returns ONLY the items whose ``workstream_id`` matches and excludes every
sibling workspace's items (the cross-decide bug from the live two-daemon demo).
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.workspace_scope import (
    WorkspaceScope,
)


def _item(request_id: str, workstream_id: str, cwd: str) -> FeedItem:
    return FeedItem(
        id=request_id,
        request_id=request_id,
        kind="question",
        workstream_id=workstream_id,
        cwd=cwd,
    )


def test_scope_keeps_only_configured_workstream_items():
    mine = "claude-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    theirs = "claude-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    scope = WorkspaceScope(
        workstream_ids=frozenset({mine}),
        cwds=frozenset({"/tmp/wt-a"}),
    )

    items = [
        _item("req-a1", mine, "/tmp/wt-a"),
        _item("req-b1", theirs, "/tmp/wt-b"),
        _item("req-a2", mine, "/tmp/wt-a"),
    ]

    kept = scope.filter(items)

    assert [i.request_id for i in kept] == ["req-a1", "req-a2"]
    # the sibling workspace's item must never reach this daemon
    assert all(i.workstream_id != theirs for i in kept)
