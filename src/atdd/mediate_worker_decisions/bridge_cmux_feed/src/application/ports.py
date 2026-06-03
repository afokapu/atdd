"""Application ports for the feed bridge (structural typing, no I/O here).

``FeedSource`` reads pending items off the cmux Feed; ``FeedReply`` delivers a
resolved reply plan back through the Feed; ``Coach`` mediates a request into a
verdict. Integration adapters and test doubles satisfy these by shape.
"""
from __future__ import annotations

from typing import List, Protocol

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    FeedItem,
    FeedReplyPlan,
)
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import Verdict
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    DecisionRequest,
)


class FeedSource(Protocol):
    def list_pending(self) -> List[FeedItem]: ...


class FeedReply(Protocol):
    def deliver(self, plan: FeedReplyPlan) -> None: ...


class Coach(Protocol):
    def mediate(self, request: DecisionRequest) -> Verdict: ...
