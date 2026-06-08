# URN: test:mediate-worker-decisions:bridge-cmux-feed:L007-INTEGRATION-002-unresolvable-surface-list-does-not-silently-empty-scope
# Acceptance: acc:mediate-worker-decisions:L007-INTEGRATION-002-unresolvable-surface-list-does-not-silently-empty-scope
# WMBT: wmbt:mediate-worker-decisions:L007
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""L007-INTEGRATION-002 — an unusable surface.list does NOT silently empty-scope.

A watched-but-empty scope is a bug, not a no-op: if ``surface.list`` returns nothing
usable for a workspace the daemon was explicitly told to watch (empty payload, no
surfaces, or garbled JSON), the source must NOT degrade to an empty scope that silently
swallows every one of that workspace's decisions. It degrades to a LOUD permissive scope
so the pending decisions still flow (and logs the miss so it is visible).
"""
from __future__ import annotations

import json
import logging

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_event_source import (
    CmuxFeedSource,
)

_FEED = {
    "items": [
        {
            "id": "i-1",
            "request_id": "req-watched",
            "kind": "question",
            "status": "pending",
            "workstream_id": "claude-33333333-3333-3333-3333-333333333333",
            "cwd": "/Users/dev/repo/feat-y",
            "question_prompt": "still pending?",
        }
    ]
}


class _EmptySurfaceRunner:
    """surface.list returns no usable surfaces for the watched workspace."""

    def __init__(self, surface_payload):
        self._surface_payload = surface_payload

    def __call__(self, *args, **kwargs):
        if args[:2] == ("rpc", "feed.list"):
            return json.dumps(_FEED)
        if args[:2] == ("rpc", "surface.list"):
            return self._surface_payload
        raise AssertionError(f"unexpected cmux call: {args}")


def test_empty_surface_list_degrades_to_permissive_not_silent_swallow(caplog):
    source = CmuxFeedSource(
        workspace_id="workspace:140",
        runner=_EmptySurfaceRunner(json.dumps({"surfaces": []})),
    )

    with caplog.at_level(logging.WARNING):
        items = source.list_pending()

    # the watched workspace's pending decision is NOT silently swallowed
    assert [i.request_id for i in items] == ["req-watched"]
    # the degrade is loud, not a silent no-op
    assert any(record.levelno >= logging.WARNING for record in caplog.records)


def test_garbled_surface_list_also_degrades_to_permissive(caplog):
    source = CmuxFeedSource(
        workspace_id="workspace:140",
        runner=_EmptySurfaceRunner("}{ not json"),
    )

    with caplog.at_level(logging.WARNING):
        items = source.list_pending()

    assert [i.request_id for i in items] == ["req-watched"]
    assert any(record.levelno >= logging.WARNING for record in caplog.records)
