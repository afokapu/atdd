# URN: test:mediate-worker-decisions:bridge-cmux-feed:L005-INTEGRATION-001-source-scopes-via-surface-list
# Acceptance: acc:mediate-worker-decisions:L005-INTEGRATION-001-source-scopes-via-surface-list
# WMBT: wmbt:mediate-worker-decisions:L005
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""L005-INTEGRATION-001 — CmuxFeedSource scopes the Feed via surface.list.

cmux ``feed.list`` is global and ignores any filter param (verified live), so the
adapter must map each global item to a workspace and keep only the configured
one's. The workspace identity (its claude session/workstream + worktree cwd) is
read from ``cmux rpc surface.list --workspace <ws>``: ``resume_binding.checkpoint_id``
is the session uuid that the item's ``workstream_id`` (``claude-<uuid>``) is built
from, and ``requested_working_directory`` is the cwd. A scoped source returns only
its workspace's pending decisions; an UNSCOPED source (no workspace_id) returns
the full global set and never calls surface.list (back-compat).
"""
from __future__ import annotations

import json

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_event_source import (
    CmuxFeedSource,
)

_MINE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_THEIRS = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

_FEED = {
    "items": [
        {
            "id": "i-a",
            "request_id": "req-a",
            "kind": "question",
            "status": "pending",
            "workstream_id": f"claude-{_MINE}",
            "cwd": "/tmp/wt-a",
            "question_prompt": "A?",
        },
        {
            "id": "i-b",
            "request_id": "req-b",
            "kind": "question",
            "status": "pending",
            "workstream_id": f"claude-{_THEIRS}",
            "cwd": "/tmp/wt-b",
            "question_prompt": "B?",
        },
        # already-executed telemetry — never a decision, always skipped
        {"id": "t", "request_id": "t", "kind": "toolUse", "status": "telemetry"},
    ]
}

_SURFACES_WS_A = {
    "surfaces": [
        {
            "ref": "surface:1",
            "type": "terminal",
            "requested_working_directory": "/tmp/wt-a",
            "resume_binding": {"kind": "claude", "checkpoint_id": _MINE},
        }
    ]
}


class _FakeRunner:
    """Dispatches cmux rpc calls by method; records which methods were called."""

    def __init__(self):
        self.methods = []

    def __call__(self, *args, **kwargs):
        self.methods.append(args)
        if args[:2] == ("rpc", "feed.list"):
            return json.dumps(_FEED)
        if args[:2] == ("rpc", "surface.list"):
            return json.dumps(_SURFACES_WS_A)
        raise AssertionError(f"unexpected cmux call: {args}")


def test_scoped_source_returns_only_its_workspace_items():
    runner = _FakeRunner()
    source = CmuxFeedSource(workspace_id="workspace:97", runner=runner)

    items = source.list_pending()

    assert [i.request_id for i in items] == ["req-a"]
    # it had to resolve the workspace identity from surface.list
    assert any(a[:2] == ("rpc", "surface.list") for a in runner.methods)


def test_unscoped_source_returns_global_set_and_skips_surface_list():
    runner = _FakeRunner()
    source = CmuxFeedSource(runner=runner)  # no workspace_id → global (back-compat)

    items = source.list_pending()

    assert {i.request_id for i in items} == {"req-a", "req-b"}
    # back-compat: an unscoped source must not pay for a surface.list resolution
    assert all(a[:2] != ("rpc", "surface.list") for a in runner.methods)
