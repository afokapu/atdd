"""FeedReply adapter: deliver a reply plan through cmux, once per request_id.

``FeedReplyApplier`` wraps a transport (anything with ``reply(verb, params)``)
behind an idempotency guard, so the same ``request_id`` is replied to exactly
once even if the runner re-delivers (WMBT E003). ``CmuxFeedTransport`` is the
real transport: it shells out via ``commons.cmux_cli.run_cmux``.
"""
from __future__ import annotations

import json
from typing import Protocol, Set

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    FeedReplyPlan,
)
from atdd.mediate_worker_decisions.commons.cmux_cli import run_cmux


class ReplyTransport(Protocol):
    def reply(self, verb: str, params: dict) -> None: ...


class InMemoryReplyGuard:
    """Tracks which request_ids have already been replied to (idempotency)."""

    def __init__(self) -> None:
        self._seen: Set[str] = set()

    def seen(self, request_id: str) -> bool:
        return request_id in self._seen

    def mark(self, request_id: str) -> None:
        self._seen.add(request_id)


class FeedReplyApplier:
    """Delivers a FeedReplyPlan through ``transport``, deduped by request_id."""

    def __init__(self, *, transport: ReplyTransport, guard: InMemoryReplyGuard) -> None:
        self._transport = transport
        self._guard = guard

    def deliver(self, plan: FeedReplyPlan) -> None:
        request_id = plan.params.get("request_id")
        if request_id is not None and self._guard.seen(request_id):
            return  # already replied — never reply twice
        self._transport.reply(plan.verb, dict(plan.params))
        if request_id is not None:
            self._guard.mark(request_id)


class CmuxFeedTransport:
    """Real transport: ``cmux rpc <verb> '<json params>'``."""

    def reply(self, verb: str, params: dict) -> None:
        run_cmux("rpc", verb, json.dumps(params))
