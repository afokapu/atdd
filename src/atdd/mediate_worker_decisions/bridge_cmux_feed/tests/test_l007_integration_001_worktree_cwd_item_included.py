# URN: test:mediate-worker-decisions:bridge-cmux-feed:L007-INTEGRATION-001-worktree-cwd-item-included
# Acceptance: acc:mediate-worker-decisions:L007-INTEGRATION-001-worktree-cwd-item-included
# WMBT: wmbt:mediate-worker-decisions:L007
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""L007-INTEGRATION-001 — a worktree-launched worker's decision is included.

A real worker is launched cmux-native at the workspace's launch cwd (.../repo/main)
and then ``cd``s into its flat-sibling git worktree (.../repo/feat-x), where it runs
claude under a NEW session uuid. So its Feed item carries a ``workstream_id`` that is
NOT the surface's ``resume_binding.checkpoint_id`` (the cmux launch/resume session) and
a cwd that is the worktree, NOT the surface's launch cwd. The scoped source must still
include it: it resolves the launch cwd's git worktrees (an injected resolver here) and
accepts the worktree the worker cd'd into. A sibling workspace's item is still excluded.
"""
from __future__ import annotations

import json

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_event_source import (
    CmuxFeedSource,
)

_LAUNCH_CWD = "/Users/dev/repo/main"
_WORKTREE_CWD = "/Users/dev/repo/feat-x"

# the cmux-managed surface session (resume checkpoint) ...
_SURFACE_SESSION = "11111111-1111-1111-1111-111111111111"
# ... is NOT the session the worker is actually running under in the worktree
_WORKER_SESSION = "22222222-2222-2222-2222-222222222222"
_SIBLING_SESSION = "99999999-9999-9999-9999-999999999999"

_FEED = {
    "items": [
        {
            "id": "i-wt",
            "request_id": "req-worktree",
            "kind": "question",
            "status": "pending",
            "workstream_id": f"claude-{_WORKER_SESSION}",
            "cwd": _WORKTREE_CWD,
            "question_prompt": "worktree?",
        },
        {
            "id": "i-other",
            "request_id": "req-sibling",
            "kind": "question",
            "status": "pending",
            "workstream_id": f"claude-{_SIBLING_SESSION}",
            "cwd": "/Users/dev/other/main",
            "question_prompt": "sibling?",
        },
    ]
}

_SURFACES = {
    "surfaces": [
        {
            "ref": "surface:1",
            "type": "terminal",
            "requested_working_directory": _LAUNCH_CWD,
            "resume_binding": {"kind": "claude", "checkpoint_id": _SURFACE_SESSION},
        }
    ]
}


class _FakeRunner:
    def __call__(self, *args, **kwargs):
        if args[:2] == ("rpc", "feed.list"):
            return json.dumps(_FEED)
        if args[:2] == ("rpc", "surface.list"):
            return json.dumps(_SURFACES)
        raise AssertionError(f"unexpected cmux call: {args}")


def _fake_worktrees(cwd: str):
    """The launch cwd's repo has two flat-sibling worktrees."""
    if cwd in (_LAUNCH_CWD, _WORKTREE_CWD):
        return [_LAUNCH_CWD, _WORKTREE_CWD]
    return []


def test_worktree_launched_item_is_included_sibling_excluded():
    source = CmuxFeedSource(
        workspace_id="workspace:140",
        runner=_FakeRunner(),
        worktrees=_fake_worktrees,
    )

    items = source.list_pending()

    # the worktree-launched worker's decision is NOT scoped out, even though its
    # workstream is unknown to the surface and its cwd is the worktree (not launch)
    assert [i.request_id for i in items] == ["req-worktree"]
    # the other workspace's item is still excluded
    assert all(i.request_id != "req-sibling" for i in items)
