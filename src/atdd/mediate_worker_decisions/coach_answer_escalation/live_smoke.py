"""Live recovery smoke harness for feature:coach-answer-escalation (#1036).

Drives the REAL operational escalation-recovery path against real substrate
(live cmux + ``claude`` worker; no mocks of external services):

  * ``answer_advances_parked_worker_live_smoke`` — a real worker blocks on an
    AskUserQuestion; ``atdd coach answer`` (the real ``AnswerEscalationUseCase``
    over ``CmuxFeedSource`` + ``CmuxFeedTransport``) delivers the operator's exact
    label and the worker advances past its menu, the Feed item resolving (E014);
  * ``wrong_label_rejected_live_smoke`` — against the same live block, a label
    that matches no option is rejected LOUDLY and NO feed reply is sent (no false
    ``delivered:true``), so the worker stays parked (C009 — the session footgun);
  * ``status_surfaces_then_omits_live_smoke`` — a REAL daemon tick escalates a
    governance sign-off into ``escalations.jsonl``; ``atdd coach status``'s
    surfacing read lists the unanswered request_id, and once it is answered the
    next read omits it (L008).

These reuse the bridge + feed_daemon live harnesses wholesale (same wagon, same
substrate). They require a real cmux + ``claude`` on PATH; the SMOKE tests skip
when cmux is absent. Each always closes the workspace it creates.
"""
from __future__ import annotations

import time
from pathlib import Path

from atdd.mediate_worker_decisions.bridge_cmux_feed.live_smoke import (
    _RecordingTransport,
    _capture,
    _cmux,
    _is_pending,
    _screen_shows_menu,
    _send_task,
    _spawn_claude_worker,
    _wait_for_pending,
    _wait_until_resolved,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import QUESTION
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_event_source import (
    CmuxFeedSource,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_reply_applier import (
    CmuxFeedTransport,
    FeedReplyApplier,
    InMemoryReplyGuard,
)
from atdd.mediate_worker_decisions.coach_answer_escalation.src.application.answer_escalation import (
    AnswerEscalationUseCase,
)
from atdd.mediate_worker_decisions.coach_answer_escalation.src.application.surface_escalations import (
    SurfaceEscalationsUseCase,
)
from atdd.mediate_worker_decisions.coach_answer_escalation.src.domain.label_resolver import (
    LabelResolutionError,
)
from atdd.mediate_worker_decisions.coach_runtime.src.integration.jsonl_escalation_reader import (
    JsonlEscalationReader,
)

_QUESTION_TASK = (
    "Use the AskUserQuestion tool right now to ask whether to indent with "
    "Tabs or Spaces (options: 'Tabs', 'Spaces'). Do nothing else first."
)
_ADVANCE_SETTLE = 12.0
_ADVANCE_INTERVAL = 1.0


def _build_use_case(source: CmuxFeedSource):
    """Real use case over a recording wrapper of the real cmux transport."""
    recorder = _RecordingTransport(CmuxFeedTransport())
    reply = FeedReplyApplier(transport=recorder, guard=InMemoryReplyGuard())
    return AnswerEscalationUseCase(source=source, reply=reply), recorder


def _wait_until_menu_gone(ws: str, surface: str) -> bool:
    deadline = time.time() + _ADVANCE_SETTLE
    while time.time() < deadline:
        if not _screen_shows_menu(_capture(ws, surface)):
            return True
        time.sleep(_ADVANCE_INTERVAL)
    return False


def answer_advances_parked_worker_live_smoke() -> dict:
    """E014 — ``atdd coach answer`` delivers the operator reply; the worker advances."""
    ws, worker = _spawn_claude_worker("atdd-1036-answer")
    try:
        _send_task(ws, worker, _QUESTION_TASK)
        source = CmuxFeedSource(workspace_id=ws)
        item = _wait_for_pending(source, kind=QUESTION)
        assert item is not None, "no pending question item appeared in the Feed"

        parked_before = _screen_shows_menu(_capture(ws, worker))
        label = item.question_options[0]["label"]  # exact option label

        use_case, recorder = _build_use_case(source)
        use_case.answer(item.request_id, label)

        delivered = any(v == "feed.question.reply" for v, _ in recorder.calls)
        item_resolved = delivered and _wait_until_resolved(source, item.request_id)
        worker_advanced = item_resolved and _wait_until_menu_gone(ws, worker)
        return {
            "delivered": delivered,
            "item_resolved": item_resolved,
            "worker_advanced": worker_advanced,
            "parked_before": parked_before,
            "request_id": item.request_id,
            "label": label,
        }
    finally:
        _cmux("close-workspace", "--workspace", ws)


def wrong_label_rejected_live_smoke() -> dict:
    """C009 — a non-exact label is rejected loudly, no feed reply, worker stays parked."""
    ws, worker = _spawn_claude_worker("atdd-1036-reject")
    try:
        _send_task(ws, worker, _QUESTION_TASK)
        source = CmuxFeedSource(workspace_id=ws)
        item = _wait_for_pending(source, kind=QUESTION)
        assert item is not None, "no pending question item appeared in the Feed"

        use_case, recorder = _build_use_case(source)
        rejected_loudly = False
        try:
            use_case.answer(item.request_id, "DefinitelyNotAnOption")
        except LabelResolutionError:
            rejected_loudly = True

        return {
            "rejected_loudly": rejected_loudly,
            "reply_delivered": bool(recorder.calls),
            "worker_still_parked": _is_pending(source, item.request_id),
            "request_id": item.request_id,
        }
    finally:
        _cmux("close-workspace", "--workspace", ws)


def status_surfaces_then_omits_live_smoke(
    tmp_dir: str = "/tmp/atdd-1036-status",
) -> dict:
    """L008 — status surfaces a real daemon escalation, then omits it once answered."""
    # Reuse the feed_daemon governance induction: a real daemon tick escalates a
    # phase sign-off into escalations.jsonl (cause=operator_reserved, no reply).
    from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.llm_coach import (
        LlmCoach,
    )
    from atdd.mediate_worker_decisions.feed_daemon.live_smoke import (
        _GOVERNANCE_TASK,
        _SpyCoach,
        _build_live_daemon,
    )

    tmp = Path(tmp_dir)
    tmp.mkdir(parents=True, exist_ok=True)
    verdicts, escalations = tmp / "verdicts.jsonl", tmp / "escalations.jsonl"
    for ledger in (verdicts, escalations):
        if ledger.exists():
            ledger.unlink()

    ws, worker = _spawn_claude_worker("atdd-1036-status")
    try:
        _send_task(ws, worker, _GOVERNANCE_TASK)
        source = CmuxFeedSource(workspace_id=ws)
        item = _wait_for_pending(source, kind=QUESTION)
        assert item is not None, "no pending governance question appeared in the Feed"

        recorder = _RecordingTransport(CmuxFeedTransport())
        daemon = _build_live_daemon(
            source=source,
            coach=_SpyCoach(LlmCoach()),
            recorder=recorder,
            verdicts=verdicts,
            escalations=escalations,
        )
        daemon.tick()  # escalates the governance sign-off into escalations.jsonl

        surfacer = SurfaceEscalationsUseCase(
            source=source, escalations=JsonlEscalationReader(escalations)
        )
        before = surfacer.surface()
        listed_before_answer = any(u.request_id == item.request_id for u in before)

        # the operator answers it via the real recovery path (atdd coach answer)
        use_case, _ = _build_use_case(source)
        label = item.question_options[0]["label"]
        use_case.answer(item.request_id, label)
        _wait_until_resolved(source, item.request_id)

        after = surfacer.surface()
        omitted_after_answer = all(u.request_id != item.request_id for u in after)
        return {
            "listed_before_answer": listed_before_answer,
            "omitted_after_answer": omitted_after_answer,
            "request_id": item.request_id,
        }
    finally:
        _cmux("close-workspace", "--workspace", ws)
