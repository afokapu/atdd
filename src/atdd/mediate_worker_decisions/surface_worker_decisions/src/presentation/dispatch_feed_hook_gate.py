"""Dispatch-time Feed-publishing-hook gate (issue #1025, WMBT E013).

Live 2026-06-09 (`atdd coach 1012`): a dispatch-spawned worker's decision
surfaced to the TUI and ``cmux rpc feed.list`` was empty — the wrapper's
PermissionRequest->'cmux hooks feed' hook never fired, so the worker hung
unmediated and the coach hung with it. The L004 probe already *warns* when the
hook path is inactive; for the dispatch spawn that warning is not enough — a
non-publishing worker must NEVER be spawned. This gate promotes the warn to a
hard refusal at dispatch spawn time.
"""
from __future__ import annotations

from typing import Any, Optional


class FeedHookInactiveError(RuntimeError):
    """Raised to refuse a dispatch spawn whose Feed-publishing hook path is inactive."""


def assert_dispatch_feed_hook_active(probe: Optional[Any] = None) -> None:
    """Refuse (raise ``FeedHookInactiveError``) when the hook path is inactive.

    ``probe`` (default: the live ``CmuxHookProbe``) reports whether the cmux
    wrapper will inject the PermissionRequest->feed hook for the worker. An
    inactive verdict means the worker's decisions would never reach the Feed, so
    the dispatch must refuse loudly instead of spawning an unmediated worker.
    """
    raise NotImplementedError  # GREEN: evaluate the probe, raise when inactive


__all__ = ["FeedHookInactiveError", "assert_dispatch_feed_hook_active"]
