"""Feed-driven runner use case: locate -> safety-gate -> mediate -> reply|escalate.

For each pending feed item the runner:
  1. (permission/exitPlan) runs the tool_input safety gate FIRST — a dangerous
     command escalates to a human and the coach is never consulted (WMBT C003);
  2. otherwise maps the item to a DecisionRequest (WMBT L002), asks the coach for
     a verdict, and delivers the reply through the Feed (WMBT E003).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.application.ports import (
    Coach,
    FeedReply,
    FeedSource,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    EXIT_PLAN,
    PERMISSION,
    FeedItem,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item_mapper import (
    map_feed_item,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_reply_mapper import (
    plan_reply,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.tool_input_safety import (
    HUMAN_REQUIRED,
    classify,
)
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    CAUSE_DANGEROUS,
    Escalation,
    Verdict,
)


@dataclass(frozen=True)
class FeedOutcome:
    """What happened for one feed item: a delivered verdict OR an escalation."""

    request_id: str
    verdict: Optional[Verdict] = None
    escalation: Optional[Escalation] = None


class FeedRunnerUseCase:
    def __init__(
        self,
        *,
        source: FeedSource,
        reply: FeedReply,
        coach: Coach,
        id_factory: Callable[[], str],
        ts_factory: Callable[[], str],
    ) -> None:
        self._source = source
        self._reply = reply
        self._coach = coach
        self._id = id_factory
        self._ts = ts_factory

    def run_once(self) -> List[FeedOutcome]:
        """Locate every pending item and handle each."""
        return [self.handle(item) for item in self._source.list_pending()]

    def handle(self, item: FeedItem) -> FeedOutcome:
        # Safety gate FIRST for tool-use kinds (WMBT C003) — before the coach.
        if item.kind in (PERMISSION, EXIT_PLAN):
            if classify(item.tool_input or "") == HUMAN_REQUIRED:
                return FeedOutcome(
                    request_id=item.request_id,
                    escalation=Escalation(
                        escalation_id=self._id(),
                        request_id=item.request_id,
                        raised_at=self._ts(),
                        cause=CAUSE_DANGEROUS,
                        safety_class=CAUSE_DANGEROUS,
                    ),
                )

        request = map_feed_item(item)
        verdict = self._coach.mediate(request)
        self._reply.deliver(plan_reply(verdict, kind=item.kind))
        return FeedOutcome(request_id=item.request_id, verdict=verdict)
