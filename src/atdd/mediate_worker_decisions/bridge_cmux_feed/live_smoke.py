"""Live-cmux Feed smoke harness for feature:bridge-cmux-feed.

Drives the REAL feed bridge against a REAL throwaway cmux workspace running a
REAL ``claude`` worker (no synthetic fixtures). The worker is given a task that
makes it block on the structured cmux Feed — an ``AskUserQuestion`` (locate /
unblock) or a permission for a dangerous command (danger). We then run the real
``FeedRunnerUseCase`` (CmuxFeedSource over ``feed.list`` + FeedReplyApplier over
``cmux rpc feed.*.reply`` + a Coach that decides by calling ``claude -p`` on the
rendered request) and observe the Feed item resolve (or escalate, no reply).

Always closes the workspace it creates. Used by the SMOKE tests, which run this
when ``cmux`` is on PATH and skip otherwise.
"""
from __future__ import annotations

import re
import subprocess
import time
from typing import List, Optional

from atdd.mediate_worker_decisions.bridge_cmux_feed.composition import (
    build_feed_runner_from_repo,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    PERMISSION,
    QUESTION,
    FeedItem,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_event_source import (
    CmuxFeedSource,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_reply_applier import (
    CmuxFeedTransport,
)
from atdd.mediate_worker_decisions.mediate_decision.src.domain.danger_rules import (
    match_danger,
)

class PermissionNotInducible(RuntimeError):
    """Raised when no *blocked* dangerous permission can be produced in the Feed.

    cmux runs workers in auto-mode (``--allow-dangerously-skip-permissions``), so
    a dangerous Bash use executes and is logged as ``toolUse`` telemetry rather
    than blocking as a pending ``permission`` decision. The C003 guarantee is
    carried by the unit + integration tests; the live SMOKE skips on this.
    """


_BOOT_SECONDS = 7.0
_FEED_TIMEOUT = 60.0
_FEED_INTERVAL = 3.0
_RESOLVE_TIMEOUT = 20.0


# --------------------------------------------------------------------------- #
# cmux helpers (mirror the wagon-root live_smoke pattern)                      #
# --------------------------------------------------------------------------- #
def _cmux(*args: str, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(["cmux", *args], capture_output=True, text=True, timeout=timeout)


def _surfaces(ws: str) -> List[str]:
    return re.findall(r"surface:\d+", _cmux("tree", "--workspace", ws).stdout)


def _spawn_claude_worker(name: str) -> tuple:
    """Create a throwaway workspace running a real claude worker; return (ws, surface)."""
    created = _cmux(
        "new-workspace", "--name", name, "--cwd", "/tmp",
        "--command", "claude", "--focus", "false",
    )
    ws = next((t for t in created.stdout.split() if t.startswith("workspace:")), None)
    if ws is None:
        raise RuntimeError(f"could not create cmux workspace: {created.stderr}")
    time.sleep(_BOOT_SECONDS)
    surfaces = _surfaces(ws)
    if not surfaces:
        raise RuntimeError("claude worker surface never appeared")
    return ws, surfaces[0]


def _send_task(ws: str, surface: str, task: str) -> None:
    _cmux("send", "--workspace", ws, "--surface", surface, task)
    _cmux("send-key", "--workspace", ws, "--surface", surface, "Enter")


def _wait_for_pending(
    source: CmuxFeedSource, *, kind: Optional[str] = None, predicate=None
) -> Optional[FeedItem]:
    deadline = time.time() + _FEED_TIMEOUT
    while time.time() < deadline:
        for item in source.list_pending():
            if kind is not None and item.kind != kind:
                continue
            if predicate is not None and not predicate(item):
                continue
            return item
        time.sleep(_FEED_INTERVAL)
    return None


def _is_pending(source: CmuxFeedSource, request_id: str) -> bool:
    return any(i.request_id == request_id for i in source.list_pending())


def _wait_until_resolved(source: CmuxFeedSource, request_id: str) -> bool:
    deadline = time.time() + _RESOLVE_TIMEOUT
    while time.time() < deadline:
        if not _is_pending(source, request_id):
            return True
        time.sleep(1.0)
    return False


# --------------------------------------------------------------------------- #
# Recording transport                                                          #
# --------------------------------------------------------------------------- #
class _RecordingTransport:
    """Wraps the real cmux transport so the smoke can prove a reply was/wasn't sent.

    The runner itself is the production wiring
    (``build_feed_runner_from_repo`` → real ``CmuxFeedSource`` + ``LlmCoach``);
    this spy is injected via the builder's ``transport`` seam so a real reply
    still goes out through ``CmuxFeedTransport`` while the smoke observes whether
    one was delivered.
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls: list = []

    def reply(self, verb: str, params: dict) -> None:
        self.calls.append((verb, params))
        self._inner.reply(verb, params)


# --------------------------------------------------------------------------- #
# The three live smokes                                                       #
# --------------------------------------------------------------------------- #
def locate_live_smoke() -> dict:
    """L002 — a real agent's blocked AskUserQuestion is located from the Feed."""
    ws, worker = _spawn_claude_worker("atdd-feed-955-locate")
    try:
        _send_task(
            ws, worker,
            "Use the AskUserQuestion tool right now to ask whether to indent with "
            "Tabs or Spaces (options: 'Tabs', 'Spaces'). Do nothing else first.",
        )
        source = CmuxFeedSource()
        item = _wait_for_pending(source, kind=QUESTION)
        assert item is not None, "no pending question item appeared in the Feed"
        from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item_mapper import (
            map_feed_item,
        )

        request = map_feed_item(item)
        return {
            "request_id": request.request_id,
            "options": [o.label for o in request.prompt.options],
        }
    finally:
        _cmux("close-workspace", "--workspace", ws)


def unblock_live_smoke() -> dict:
    """E003 — a coach verdict replied via the Feed unblocks the real agent."""
    ws, worker = _spawn_claude_worker("atdd-feed-955-unblock")
    try:
        _send_task(
            ws, worker,
            "Use the AskUserQuestion tool right now to ask whether to indent with "
            "Tabs or Spaces (options: 'Tabs', 'Spaces'). Do nothing else first.",
        )
        source = CmuxFeedSource()
        item = _wait_for_pending(source, kind=QUESTION)
        assert item is not None, "no pending question item appeared in the Feed"

        recorder = _RecordingTransport(CmuxFeedTransport())
        runner = build_feed_runner_from_repo(workspace_id=ws, transport=recorder)
        runner.run_once()

        replied = any(v == "feed.question.reply" for v, _ in recorder.calls)
        resolved = replied and _wait_until_resolved(source, item.request_id)
        return {"resolved": resolved, "request_id": item.request_id}
    finally:
        _cmux("close-workspace", "--workspace", ws)


def multi_question_unblock_live_smoke() -> dict:
    """L003/E006/E007 — a real multi-question + checkbox auto-answers ALL of it.

    The headline #976 proof: a worker blocked on ONE AskUserQuestion carrying
    three questions (single + single + multi-select checkbox) is located as a
    full block document (L003), the LlmCoach decides EVERY block (E006), and the
    flat reply carries the chosen labels for every question — checkbox included —
    so the whole item resolves and the worker proceeds (E007). No human in the
    TUI; the verdict is recorded by the daemon path.
    """
    from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item_mapper import (
        map_feed_item,
    )

    ws, worker = _spawn_claude_worker("atdd-feed-976-multi")
    try:
        _send_task(
            ws, worker,
            "Use the AskUserQuestion tool right now to ask THREE questions in one "
            "call: (1) Color, single-select, options Blue/Red; (2) Size, "
            "single-select, options Small/Large; (3) Features, multi-select "
            "(checkbox), options Auth/Billing/Cache. Do nothing else first.",
        )
        source = CmuxFeedSource()
        # wait for a genuinely multi-question item (questions[] carries >= 2)
        item = _wait_for_pending(
            source, kind=QUESTION, predicate=lambda i: len(i.questions) >= 2
        )
        assert item is not None, "no multi-question item appeared in the Feed"

        document = map_feed_item(item).document  # L003: located as a block doc
        blocks = list(document.blocks) if document else []

        recorder = _RecordingTransport(CmuxFeedTransport())
        runner = build_feed_runner_from_repo(workspace_id=ws, transport=recorder)
        outcomes = runner.run_once()

        outcome = next((o for o in outcomes if o.request_id == item.request_id), None)
        answer = outcome.verdict.answer if (outcome and outcome.verdict) else None
        answered_blocks = list(answer.answers) if answer else []

        reply = next(
            (p for v, p in recorder.calls if v == "feed.question.reply"), None
        )
        selections = list(reply.get("selections", [])) if reply else []
        resolved = reply is not None and _wait_until_resolved(source, item.request_id)
        return {
            "request_id": item.request_id,
            "questions_located": len(blocks),          # L003
            "blocks_answered": len(answered_blocks),    # E006
            "selections": selections,                   # E007 (flat, all questions)
            "resolved": resolved,                       # E007 (worker proceeds)
        }
    finally:
        _cmux("close-workspace", "--workspace", ws)


def danger_live_smoke() -> dict:
    """C003 — a real agent's dangerous tool use is escalated, never auto-replied."""
    ws, worker = _spawn_claude_worker("atdd-feed-955-danger")
    try:
        _send_task(
            ws, worker,
            "Use the Bash tool to run exactly: git push origin main . "
            "Request permission for it now; do not run anything else.",
        )
        source = CmuxFeedSource()
        item = _wait_for_pending(
            source,
            kind=PERMISSION,
            predicate=lambda i: match_danger(i.tool_input or "") is not None,
        )
        if item is None:
            raise PermissionNotInducible(
                "no blocked dangerous permission appeared in the Feed under cmux auto-mode"
            )

        recorder = _RecordingTransport(CmuxFeedTransport())
        runner = build_feed_runner_from_repo(workspace_id=ws, transport=recorder)
        outcomes = runner.run_once()

        escalated = next(
            (o for o in outcomes if o.request_id == item.request_id and o.escalation), None
        )
        assert escalated is not None, "dangerous item was not escalated"
        return {
            "cause": escalated.escalation.cause,
            "auto_replied": bool(recorder.calls),
        }
    finally:
        _cmux("close-workspace", "--workspace", ws)
