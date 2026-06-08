"""WorkspaceScope — pure membership predicate for per-workspace feed scoping.

The cmux Feed is global: ``feed.list`` returns every worker's pending decisions
and ignores any filter param (verified live). A per-workspace daemon must act on
ONLY its own workspace's decisions, else N daemons each decide every worker's
prompt (the live two-daemon cross-decide bug — two ``auto_apply`` verdicts with
the same ``request_id``). This value object holds the configured workspace's
identity — the set of ``workstream_id``s (the precise claude-session signal) and
the set of worktree ``cwd``s (the fallback) — and decides whether a given
``FeedItem`` belongs to it. It is pure data: the cmux-specific resolution of that
identity (``surface.list``) lives in the integration tier.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, List

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem


@dataclass(frozen=True)
class WorkspaceScope:
    """Decides whether a feed item belongs to the configured workspace.

    ``workstream_ids`` is the precise signal — each is a ``claude-<session-uuid>``
    that an item's ``workstream_id`` must match exactly. ``cwds`` is the fallback,
    used when an item's workstream is unknown to us: a real spawned worker runs in
    a unique worktree, so its cwd isolates it. Because a worker is launched at a
    repo's launch cwd and then ``cd``s into a flat-sibling worktree (running claude
    under a NEW session that is NOT the surface's resume checkpoint), the cwds set
    is resolved worktree-aware in the integration tier — it carries both the launch
    cwd AND the repo's worktree dirs, so the worktree the worker cd'd into matches.

    ``permissive`` is the watched-but-unresolvable degrade (WMBT L007): when the
    integration tier cannot resolve ANY identity for a workspace the daemon was
    explicitly told to watch (e.g. ``surface.list`` returned nothing usable), it
    builds a permissive scope that owns EVERY item rather than an empty scope that
    silently swallows the watched workspace's decisions. A watched-but-empty scope
    is a bug, not a no-op — over-including is recoverable; silent swallowing parks
    the worker forever.
    """

    workstream_ids: FrozenSet[str]
    cwds: FrozenSet[str]
    permissive: bool = False

    def owns(self, item: FeedItem) -> bool:
        # Watched-but-unresolvable degrade: never silently swallow the decisions of
        # a workspace we were told to watch (WMBT L007).
        if self.permissive:
            return True
        # Precise: the claude session/workstream this item was raised by.
        if item.workstream_id and item.workstream_id in self.workstream_ids:
            return True
        # Fallback: the worktree cwd, when the item's workstream is unknown to us
        # (e.g. a worktree-launched worker running under a session that is not the
        # surface's resume checkpoint — the cwds set is worktree-aware).
        if item.cwd and item.cwd in self.cwds:
            return True
        return False

    def filter(self, items: List[FeedItem]) -> List[FeedItem]:
        return [item for item in items if self.owns(item)]
