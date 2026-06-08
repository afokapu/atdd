# URN: test:mediate-worker-decisions:bridge-cmux-feed:L007-UNIT-001-permissive-scope-owns-every-item
# Acceptance: acc:mediate-worker-decisions:L007-UNIT-001-permissive-scope-owns-every-item
# WMBT: wmbt:mediate-worker-decisions:L007
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""L007-UNIT-001 — a permissive scope owns every item (the watched-but-empty degrade).

When ``surface.list`` yields no usable identity for a workspace the daemon was
explicitly told to watch, scoping it to an empty set silently swallows every one
of that workspace's decisions — a bug, not a no-op. The pure ``WorkspaceScope``
exposes a ``permissive`` mode for that degrade: it owns EVERY item rather than
dropping the watched workspace's decisions. A normal (non-permissive) scope still
excludes a sibling workspace's item.
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


def test_permissive_scope_owns_every_item_while_strict_excludes_sibling():
    mine = "claude-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    theirs = "claude-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    items = [
        _item("req-a", mine, "/tmp/wt-a"),
        _item("req-b", theirs, "/tmp/wt-b"),
    ]

    # the watched-but-unresolvable degrade: no identity resolved, but it must NOT
    # silently swallow the watched workspace's decisions
    permissive = WorkspaceScope(frozenset(), frozenset(), permissive=True)
    assert [i.request_id for i in permissive.filter(items)] == ["req-a", "req-b"]

    # a normal resolved scope still isolates its own workspace
    strict = WorkspaceScope(frozenset({mine}), frozenset({"/tmp/wt-a"}))
    assert [i.request_id for i in strict.filter(items)] == ["req-a"]
    assert all(i.workstream_id != theirs for i in strict.filter(items))
