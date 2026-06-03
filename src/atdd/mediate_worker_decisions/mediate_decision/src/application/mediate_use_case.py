"""Mediate use case: safety gate FIRST, then a bounded coach dialogue.

Order is the safety invariant: a dangerous request is escalated and the coach
client is NEVER called (WMBT C002). Coach silence escalates on a Clock-driven
timeout rather than waiting forever or applying a default (WMBT M001). A coach
reply that is unparseable or selects an option not on offer escalates as
``coach_unparseable`` (WMBT E001/Y001).
"""
from __future__ import annotations

from typing import Callable, Union

from atdd.mediate_worker_decisions.mediate_decision.src.application.ports import (
    Clock,
    CoachClient,
    EscalationSink,
    VerdictSink,
)
from atdd.mediate_worker_decisions.mediate_decision.src.domain.coach_reply_parser import (
    CoachReplyParseError,
    parse_reply,
    selection_in_options,
)
from atdd.mediate_worker_decisions.mediate_decision.src.domain.safety_classifier import (
    classify,
)
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    AUTO_APPLY,
    CAUSE_DANGEROUS,
    CAUSE_TIMEOUT,
    CAUSE_UNPARSEABLE,
    SOURCE_COACH,
    Escalation,
    Verdict,
)

Outcome = Union[Verdict, Escalation]


def build_coach_request(request: object) -> str:
    """Render a request the coach can answer with DECISION:/REASON: (WMBT P001)."""
    prompt = request.prompt  # type: ignore[attr-defined]
    options = "\n".join(f"  {o.id}) {o.label}" for o in prompt.options)
    return (
        "ATDD COACH DECISION REQUEST\n"
        f"Worker surface: {request.worker.surface_id}\n"  # type: ignore[attr-defined]
        f"Question:\n  {prompt.question}\n"
        f"Options:\n{options}\n\n"
        "Reply exactly:\n"
        "DECISION: <option-id>\n"
        "REASON: <one sentence>\n"
    )


class MediateDecisionUseCase:
    def __init__(
        self,
        coach: CoachClient,
        clock: Clock,
        verdict_sink: VerdictSink,
        escalation_sink: EscalationSink,
        id_factory: Callable[[], str],
        ts_factory: Callable[[], str],
        timeout_seconds: float = 180.0,
        poll_interval: float = 2.0,
        renderer: Callable[[object], str] = build_coach_request,
    ) -> None:
        self._coach = coach
        self._clock = clock
        self._verdicts = verdict_sink
        self._escalations = escalation_sink
        self._id = id_factory
        self._now = ts_factory
        self._timeout = timeout_seconds
        self._poll = poll_interval
        self._render = renderer

    def handle(self, request: object) -> Outcome:
        prompt = request.prompt  # type: ignore[attr-defined]

        # 1) Safety gate — BEFORE any coach contact.
        safety = classify(prompt.question, [o.label for o in prompt.options])
        if not safety.is_safe:
            return self._escalate(
                request, CAUSE_DANGEROUS, safety_class=safety.matched_rule
            )

        # 2) Coach dialogue, bounded by the clock.
        self._coach.present(self._render(request))
        option_ids = [o.id for o in prompt.options]
        deadline = self._clock.now() + self._timeout
        last_seen = None
        while self._clock.now() < deadline:
            text = self._coach.read_reply()
            if text != last_seen:
                last_seen = text
                try:
                    decision_id, reason = parse_reply(text)
                except CoachReplyParseError:
                    self._clock.sleep(self._poll)
                    continue
                if not selection_in_options(decision_id, option_ids):
                    return self._escalate(request, CAUSE_UNPARSEABLE)
                return self._emit_verdict(request, decision_id, reason)
            self._clock.sleep(self._poll)

        # 3) Silence -> escalate, never silent-apply.
        return self._escalate(request, CAUSE_TIMEOUT)

    def _emit_verdict(self, request: object, decision_id: str, reason: str) -> Verdict:
        verdict = Verdict(
            verdict_id=self._id(),
            request_id=request.request_id,  # type: ignore[attr-defined]
            decided_at=self._now(),
            disposition=AUTO_APPLY,
            source=SOURCE_COACH,
            selected_option_id=decision_id,
            reason=reason,
        )
        self._verdicts.emit(verdict)
        return verdict

    def _escalate(self, request: object, cause: str, safety_class=None) -> Escalation:
        escalation = Escalation(
            escalation_id=self._id(),
            request_id=request.request_id,  # type: ignore[attr-defined]
            raised_at=self._now(),
            cause=cause,
            safety_class=safety_class,
            human_channel_ref=request.worker.surface_id,  # type: ignore[attr-defined]
        )
        self._escalations.emit(escalation)
        return escalation
