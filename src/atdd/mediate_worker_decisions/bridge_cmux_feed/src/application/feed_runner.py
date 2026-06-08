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
    WorkerAdvance,
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
    DANGEROUS_DENY,
    DANGEROUS_ESCALATE,
    plan_permission_deny,
    plan_reply,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.tool_input_safety import (
    HUMAN_REQUIRED,
    classify,
    is_dangerous,
)
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    CAUSE_DANGEROUS,
    CAUSE_WORKER_STUCK,
    Escalation,
    Verdict,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_document import (
    CONFIRM,
    DecisionDocument,
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
        dangerous_permission_policy: str = DANGEROUS_ESCALATE,
        advance: Optional[WorkerAdvance] = None,
    ) -> None:
        self._source = source
        self._reply = reply
        self._coach = coach
        self._id = id_factory
        self._ts = ts_factory
        # Optional advance-verifier (#986). When wired (production coach/daemon),
        # the runner proves the worker actually proceeded after the reply, with a
        # send-key fallback and a worker_stuck escalation if it stays parked. Left
        # None in tests/wirings that only exercise reply delivery (back-compat).
        self._advance = advance
        # How a dangerous PERMISSION request is resolved without a human (#981).
        # Default ESCALATE preserves the supervised human-in-the-loop behavior;
        # the autonomous daemon passes DENY so a dangerous action is blocked
        # immediately rather than stalling the worker at the 120s soft-wait.
        self._dangerous_policy = dangerous_permission_policy

    def run_once(self) -> List[FeedOutcome]:
        """Locate every pending item and handle each."""
        return [self.handle(item) for item in self._source.list_pending()]

    def handle(self, item: FeedItem) -> FeedOutcome:
        # Safety gate FIRST for tool-use kinds (WMBT C003) — before the coach.
        if item.kind in (PERMISSION, EXIT_PLAN) and classify(item.tool_input or "") == HUMAN_REQUIRED:
            return self._resolve_dangerous_tool_use(item)

        request = map_feed_item(item)

        # Document-level per-block safety (WMBT C005): a dangerous confirm block
        # within a multi-block document escalates the WHOLE document — a cmux
        # item is answered atomically, so it is never partially replied. The
        # coach is not consulted for a document carrying a dangerous block.
        if request.document is not None and _has_dangerous_block(request.document):
            return self._escalate(item.request_id)

        verdict = self._coach.mediate(request)
        self._reply.deliver(plan_reply(verdict, kind=item.kind))
        return self._confirm_or_recover(item, verdict)

    def _confirm_or_recover(self, item: FeedItem, verdict: Verdict) -> FeedOutcome:
        """Prove the worker advanced; send-key fallback then escalate if stuck (#986).

        A delivered reply is NOT proof the worker proceeded — a cmux-native worker
        can lose the race against its native TUI menu and stay parked while the
        Feed item is marked non-pending (the false ``expired`` signal). When an
        advance-verifier is wired (production coach/daemon), confirm the worker
        actually advanced; if not, deliver the pre-highlighted selection via a
        send-key nudge and re-verify; if it is STILL parked, escalate
        ``worker_stuck`` rather than silently claim the reply landed. Without a
        verifier (delivery-only wirings) the behavior is unchanged.
        """
        verdict_outcome = FeedOutcome(request_id=item.request_id, verdict=verdict)
        if self._advance is None:
            return verdict_outcome
        if self._advance.confirm_advanced(item):
            return verdict_outcome
        self._advance.nudge(item)
        if self._advance.confirm_advanced(item):
            return verdict_outcome
        return self._escalate(item.request_id, cause=CAUSE_WORKER_STUCK, safety_class=None)

    def _resolve_dangerous_tool_use(self, item: FeedItem) -> FeedOutcome:
        """Resolve a tool use the safety gate flagged dangerous (WMBT C003).

        A dangerous action is NEVER auto-approved and the coach is never consulted.
        The coach policy resolves it without a human reply: under ``deny`` the
        PERMISSION request is actively denied via the Feed (autonomous-safe — no
        120s soft-wait stall); under ``escalate`` no reply is sent and a human
        decides. Either way the escalation is recorded. Only a PERMISSION item has
        a deny-reply shape; EXIT_PLAN escalates only.
        """
        if item.kind == PERMISSION and self._dangerous_policy == DANGEROUS_DENY:
            self._reply.deliver(plan_permission_deny(item.request_id))
        return self._escalate(item.request_id)

    def _escalate(
        self,
        request_id: str,
        cause: str = CAUSE_DANGEROUS,
        safety_class: Optional[str] = CAUSE_DANGEROUS,
    ) -> FeedOutcome:
        return FeedOutcome(
            request_id=request_id,
            escalation=Escalation(
                escalation_id=self._id(),
                request_id=request_id,
                raised_at=self._ts(),
                cause=cause,
                safety_class=safety_class,
            ),
        )


def _has_dangerous_block(document: DecisionDocument) -> bool:
    """A confirm block whose prompt matches a danger pattern makes the whole
    document human-required (WMBT C005). Group compositions are flattened by
    ``leaf_blocks`` so a dangerous block nested in a group is still caught.

    A confirm-block prompt is prose, not a shell command, so it is checked with
    the danger-pattern matcher — NOT the allowlist command gate (``classify``),
    which escalates-by-default and would force every benign confirm to a human
    (#1014)."""
    return any(
        block.kind == CONFIRM and is_dangerous(block.prompt)
        for block in document.leaf_blocks()
    )
