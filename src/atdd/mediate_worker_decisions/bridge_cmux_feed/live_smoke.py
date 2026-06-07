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
import tempfile
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
from atdd.mediate_worker_decisions.commons.cmux_cli import strip_ansi

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


def _spawn_claude_worker(name: str, cwd: str = "/tmp") -> tuple:
    """Create a throwaway workspace running a real claude worker; return (ws, surface)."""
    created = _cmux(
        "new-workspace", "--name", name, "--cwd", cwd,
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


def _spawn_claude_native_worker(name: str, prompt: str) -> tuple:
    """Spawn the cmux-NATIVE launch path that reproduces the #986 race.

    Unlike ``_spawn_claude_worker`` (plain ``claude`` then a ``send`` of the
    task), this embeds the prompt in the launch ``--command`` exactly as the
    coach launches workers, so claude renders its native interactive question
    menu — the configuration where a Feed reply loses the race and the worker
    stays parked. Returns (workspace_ref, surface_ref).
    """
    created = _cmux(
        "new-workspace", "--name", name, "--cwd", "/tmp", "--focus", "false",
        "--command",
        f'claude "{prompt}" --permission-mode acceptEdits --allowedTools "Read"',
    )
    ws = next((t for t in created.stdout.split() if t.startswith("workspace:")), None)
    if ws is None:
        raise RuntimeError(f"could not create cmux workspace: {created.stderr}")
    time.sleep(_BOOT_SECONDS)
    surfaces = _surfaces(ws)
    if not surfaces:
        raise RuntimeError("claude worker surface never appeared")
    return ws, surfaces[0]


def _capture(ws: str, surface: str) -> str:
    return strip_ansi(_cmux("capture-pane", "--workspace", ws, "--surface", surface).stdout)


def _screen_shows_menu(text: str) -> bool:
    """The worker is still parked iff its native question menu is on screen."""
    return "Enter to select" in text


def _screen_shows_answered(text: str) -> bool:
    return "User answered" in text or "You chose" in text


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


def scope_isolation_live_smoke(evidence_path: Optional[str] = None) -> dict:
    """L005 — two live workers, each scoped consumer sees ONLY its own (#993).

    The headline #993 proof. Spawns TWO real claude workers in TWO workspaces,
    each in its OWN throwaway worktree cwd (faithful to how the coach spawns real
    workers), and blocks each on a DISTINCT AskUserQuestion. Builds a
    workspace-scoped ``CmuxFeedSource`` for each and asserts each sees ONLY its
    own worker's pending decision — no cross-decide, and no duplicate
    ``request_id`` across the two scoped result sets (the live two-daemon bug).
    The scope is resolved per workspace from ``surface.list`` (the claude session
    workstream is the precise signal; the distinct worktree cwd corroborates).

    Captures a screen/identity evidence artifact (#983 evidence-bound smokes) and
    always closes both workspaces. Runs in throwaway /tmp scratch dirs, never the
    caller's worktree.
    """
    question_a = (
        "Use the AskUserQuestion tool right now to ask whether to indent with "
        "Tabs or Spaces (options: Tabs, Spaces). Do nothing else first."
    )
    question_b = (
        "Use the AskUserQuestion tool right now to ask whether you prefer "
        "Cats or Dogs (options: Cats, Dogs). Do nothing else first."
    )
    cwd_a = tempfile.mkdtemp(prefix="atdd-993-a-")
    cwd_b = tempfile.mkdtemp(prefix="atdd-993-b-")
    ws_a, worker_a = _spawn_claude_worker("atdd-993-scope-a", cwd=cwd_a)
    try:
        ws_b, worker_b = _spawn_claude_worker("atdd-993-scope-b", cwd=cwd_b)
        try:
            _send_task(ws_a, worker_a, question_a)
            _send_task(ws_b, worker_b, question_b)

            # Each scoped source must surface ONLY its own workspace's decision.
            source_a = CmuxFeedSource(workspace_id=ws_a)
            source_b = CmuxFeedSource(workspace_id=ws_b)
            item_a = _wait_for_pending(source_a, kind=QUESTION)
            item_b = _wait_for_pending(source_b, kind=QUESTION)
            assert item_a is not None, "workspace A scoped source saw no decision"
            assert item_b is not None, "workspace B scoped source saw no decision"

            # Re-read the full scoped sets to prove the isolation both ways.
            a_ids = sorted({i.request_id for i in source_a.list_pending()})
            b_ids = sorted({i.request_id for i in source_b.list_pending()})
            shared = sorted(set(a_ids) & set(b_ids))

            if evidence_path:
                with open(evidence_path, "w", encoding="utf-8") as fh:
                    fh.write("=== #993 workspace-scope isolation ===\n")
                    fh.write(f"workspace A: {ws_a}  cwd={cwd_a}\n")
                    fh.write(f"  scoped request_id: {item_a.request_id}\n")
                    fh.write(f"  workstream_id: {item_a.workstream_id}\n")
                    fh.write(f"  A scoped set: {a_ids}\n\n")
                    fh.write(f"workspace B: {ws_b}  cwd={cwd_b}\n")
                    fh.write(f"  scoped request_id: {item_b.request_id}\n")
                    fh.write(f"  workstream_id: {item_b.workstream_id}\n")
                    fh.write(f"  B scoped set: {b_ids}\n\n")
                    fh.write(f"shared request_ids (must be empty): {shared}\n")

            return {
                "a_request_id": item_a.request_id,
                "b_request_id": item_b.request_id,
                "a_seen_request_ids": a_ids,
                "b_seen_request_ids": b_ids,
                "shared_request_ids": shared,
                "evidence_path": evidence_path,
            }
        finally:
            _cmux("close-workspace", "--workspace", ws_b)
    finally:
        _cmux("close-workspace", "--workspace", ws_a)


def advance_live_smoke(evidence_path: Optional[str] = None) -> dict:
    """E009 — a cmux-native worker ACTUALLY proceeds after a Feed reply (#986).

    The headline #986 proof. Spawns the cmux-native launch path that reproduces
    the race (claude renders its native interactive menu), blocks it on an
    AskUserQuestion, then drives the REAL production runner — which now verifies
    the worker advanced and send-keys the pre-highlighted selection as a fallback
    if the Feed reply alone did not unblock it. Asserts the worker's screen
    advances past the menu (not merely that the Feed item resolved), and captures
    a screen-before/after evidence artifact (#983 evidence-bound smokes).
    """
    from atdd.mediate_worker_decisions.bridge_cmux_feed.composition import (
        build_feed_runner_from_repo,
    )

    prompt = (
        "Use the AskUserQuestion tool right now to ask whether to indent with "
        "Tabs or Spaces (options: Tabs, Spaces). Do nothing else first."
    )
    ws, worker = _spawn_claude_native_worker("atdd-feed-986-advance", prompt)
    try:
        source = CmuxFeedSource()
        item = _wait_for_pending(source, kind=QUESTION)
        assert item is not None, "no pending question item appeared in the Feed"

        screen_before = _capture(ws, worker)
        assert _screen_shows_menu(screen_before), (
            "worker did not render the native question menu — wrong launch path"
        )

        # Production wiring now includes the WorkerAdvance verifier+fallback.
        runner = build_feed_runner_from_repo(workspace_id=ws)
        runner.run_once()

        # Give the (possible) send-key fallback a moment to land, then re-read.
        time.sleep(3.0)
        screen_after = _capture(ws, worker)

        advanced = _screen_shows_answered(screen_after) or not _screen_shows_menu(
            screen_after
        )

        if evidence_path:
            with open(evidence_path, "w", encoding="utf-8") as fh:
                fh.write("=== request_id ===\n")
                fh.write(item.request_id + "\n\n")
                fh.write("=== screen BEFORE reply (parked on menu) ===\n")
                fh.write(screen_before + "\n\n")
                fh.write("=== screen AFTER reply+fallback (advanced) ===\n")
                fh.write(screen_after + "\n")

        return {
            "request_id": item.request_id,
            "parked_before": _screen_shows_menu(screen_before),
            "advanced": advanced,
            "evidence_path": evidence_path,
        }
    finally:
        _cmux("close-workspace", "--workspace", ws)


def decide_with_convention_live_smoke(evidence_path: Optional[str] = None) -> dict:
    """E011 — a live decider answers a benign question WITH the coach convention loaded.

    The headline #987 (b) proof. Spawns a real claude worker blocked on a benign
    AskUserQuestion, then drives the REAL runner whose ``LlmCoach`` carries the
    repo coach convention / operating protocol into its ``claude -p`` call. A thin
    recorder wraps the production claude provider CLI so the smoke captures the
    EXACT system context the decider was handed (evidence per #983) while a real
    ``claude -p`` still decides. Asserts BOTH: a verdict was produced AND the coach
    convention was present in the decider's invocation.
    """
    from atdd.mediate_worker_decisions.bridge_cmux_feed.composition import (
        build_feed_runner,
    )
    from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.coach_context import (
        load_coach_context,
    )
    from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.llm_coach import (
        LlmCoach,
        resolve_provider_cli,
    )
    from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_advance_verifier import (
        CmuxWorkerAdvance,
    )

    coach_context = load_coach_context()
    real_cli = resolve_provider_cli("claude", None)
    captured: dict = {}

    def _recording_claude_cli(prompt, *, system=None, timeout):
        captured["system"] = system  # what the decider was actually handed
        return real_cli(prompt, system=system, timeout=timeout)

    ws, worker = _spawn_claude_worker("atdd-feed-987-convention")
    try:
        _send_task(
            ws, worker,
            "Use the AskUserQuestion tool right now to ask whether to indent with "
            "Tabs or Spaces (options: 'Tabs', 'Spaces'). Do nothing else first.",
        )
        source = CmuxFeedSource(workspace_id=ws)
        item = _wait_for_pending(source, kind=QUESTION)
        assert item is not None, "no pending question item appeared in the Feed"

        recorder = _RecordingTransport(CmuxFeedTransport())
        coach = LlmCoach(cli=_recording_claude_cli, coach_context=coach_context)
        runner = build_feed_runner(
            source=source,
            reply=recorder,
            coach=coach,
            advance=CmuxWorkerAdvance(workspace_id=ws),
        )
        outcomes = runner.run_once()

        outcome = next((o for o in outcomes if o.request_id == item.request_id), None)
        verdict_produced = bool(outcome and outcome.verdict is not None)
        system_seen = captured.get("system") or ""
        convention_present = "Phase Machine Convention" in system_seen

        if evidence_path:
            with open(evidence_path, "w", encoding="utf-8") as fh:
                fh.write("=== #987(b) decide-with-convention ===\n")
                fh.write(f"request_id: {item.request_id}\n")
                fh.write(f"verdict_produced: {verdict_produced}\n")
                fh.write(f"convention_present: {convention_present}\n\n")
                fh.write("=== coach context handed to the decider (head) ===\n")
                fh.write(system_seen[:800] + "\n")

        return {
            "request_id": item.request_id,
            "verdict_produced": verdict_produced,       # a verdict was produced
            "convention_present": convention_present,   # convention reached the decider
            "evidence_path": evidence_path,
        }
    finally:
        _cmux("close-workspace", "--workspace", ws)
