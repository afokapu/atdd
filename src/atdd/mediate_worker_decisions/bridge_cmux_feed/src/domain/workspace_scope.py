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
    used when an item carries no resolvable ``workstream_id``: a real spawned
    worker runs in a unique worktree, so its cwd isolates it (the documented
    limitation is two workers sharing a cwd — real workers get distinct worktrees).
    """

    workstream_ids: FrozenSet[str]
    cwds: FrozenSet[str]

    def owns(self, item: FeedItem) -> bool:
        # Precise: the claude session/workstream this item was raised by.
        if item.workstream_id and item.workstream_id in self.workstream_ids:
            return True
        # Fallback: the worktree cwd, when the item's workstream is unknown to us
        # (e.g. the surface had no resume binding to resolve a session uuid).
        if item.cwd and item.cwd in self.cwds:
            return True
        return False

    def filter(self, items: List[FeedItem]) -> List[FeedItem]:
        return [item for item in items if self.owns(item)]
