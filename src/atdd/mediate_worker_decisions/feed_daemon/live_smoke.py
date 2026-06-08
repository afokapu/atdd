"""Live smoke harness for feature:feed-daemon.

Drives the REAL daemon (``FeedDaemonUseCase``) — the continuous loop around the
bridge decide/escalate brain — against real substrate:

  * ``loop_answers_live_smoke``      — one tick answers a real blocked question
                                       and the agent is unblocked (WMBT E004);
  * ``danger_escalates_live_smoke``  — a real dangerous tool_input is recorded +
                                       loud-logged and NEVER auto-answered, with
                                       the coach never consulted (WMBT C004 —
                                       the critical safety smoke);
  * ``restart_no_double_answer_live_smoke`` — a daemon restarted against the same
                                       durable ledgers re-escalates NOTHING for an
                                       already-handled, still-blocked item (E005);
  * ``sigterm_clean_shutdown_live_smoke``   — a real daemon process exits and
                                       releases its lock on SIGTERM (WMBT R002);
  * ``second_instance_refused_live_smoke``  — a second real daemon process refuses
                                       to start while the first holds the lock (D002).

The first three need a real cmux + ``claude`` (skip when ``cmux`` is absent). The
last two are process-level and need neither — they spawn the daemon as a real
subprocess via this interpreter.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

# Reuse the bridge's live cmux/worker harness wholesale — same wagon, same
# substrate; no need to reinvent workspace spawn / Feed polling.
from atdd.mediate_worker_decisions.bridge_cmux_feed.live_smoke import (
    PermissionNotInducible,
    _RecordingTransport,
    _cmux,
    _send_task,
    _spawn_claude_worker,
    _wait_for_pending,
    _wait_until_resolved,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.composition import build_feed_runner
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.llm_coach import (
    LlmCoach,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (
    PERMISSION,
    QUESTION,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_event_source import (
    CmuxFeedSource,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_reply_applier import (
    CmuxFeedTransport,
)
from atdd.mediate_worker_decisions.feed_daemon.composition import build_feed_daemon
from atdd.mediate_worker_decisions.feed_daemon.src.domain.answered_set import AnsweredSet
from atdd.mediate_worker_decisions.feed_daemon.src.integration.jsonl_ledgers import (
    JsonlEscalationSink,
    JsonlVerdictLedger,
    read_handled_request_ids,
)
from atdd.mediate_worker_decisions.feed_daemon.src.integration.pidfile_lock import (
    PidfileLock,
)
from atdd.mediate_worker_decisions.feed_daemon.src.integration.signal_stop import (
    RealSleeper,
)
from atdd.mediate_worker_decisions.mediate_decision.src.domain.danger_rules import (
    match_danger,
)

_QUESTION_TASK = (
    "Use the AskUserQuestion tool right now to ask whether to indent with "
    "Tabs or Spaces (options: 'Tabs', 'Spaces'). Do nothing else first."
)
_DANGER_TASK = (
    "Use the Bash tool to run exactly: git push origin main . "
    "Request permission for it now; do not run anything else."
)

_PROC_BOOT_TIMEOUT = 10.0
_PROC_EXIT_TIMEOUT = 10.0


# --------------------------------------------------------------------------- #
# Spies that prove the safety invariants without changing behaviour            #
# --------------------------------------------------------------------------- #
class _NeverStop:
    """stop signal for the tick-only smokes (run_forever is not exercised)."""

    def is_set(self) -> bool:
        return False


class _SpyCoach:
    """Wraps a coach to PROVE whether it was consulted (dangerous path: never)."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls: list = []

    def mediate(self, request):
        self.calls.append(request)
        return self._inner.mediate(request)


class _ListHandler(logging.Handler):
    """Captures WARNING+ records emitted on the daemon's logger (loud-log proof)."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _build_live_daemon(*, source, coach, recorder, verdicts: Path, escalations: Path):
    runner = build_feed_runner(source=source, reply=recorder, coach=coach)
    return build_feed_daemon(
        source=source,
        runner=runner,
        escalation_sink=JsonlEscalationSink(escalations),
        verdict_ledger=JsonlVerdictLedger(verdicts),
        sleeper=RealSleeper(),
        stop=_NeverStop(),
        lock=PidfileLock(escalations.parent / "feed-daemon.lock"),
        answered=AnsweredSet(read_handled_request_ids(verdicts, escalations)),
    )


# --------------------------------------------------------------------------- #
# cmux + claude smokes (coach runs these on live substrate)                    #
# --------------------------------------------------------------------------- #
def loop_answers_live_smoke(tmp_dir: str = "/tmp/atdd-feed-daemon-loop") -> dict:
    """E004 — one real daemon tick answers a blocked agent and unblocks it."""
    tmp = Path(tmp_dir)
    tmp.mkdir(parents=True, exist_ok=True)
    verdicts, escalations = tmp / "verdicts.jsonl", tmp / "escalations.jsonl"
    ws, worker = _spawn_claude_worker("atdd-feed-966-loop")
    try:
        _send_task(ws, worker, _QUESTION_TASK)
        source = CmuxFeedSource()
        item = _wait_for_pending(source, kind=QUESTION)
        assert item is not None, "no pending question item appeared in the Feed"

        recorder = _RecordingTransport(CmuxFeedTransport())
        daemon = _build_live_daemon(
            source=source, coach=LlmCoach(), recorder=recorder,
            verdicts=verdicts, escalations=escalations,
        )
        daemon.tick()

        replied = any(v == "feed.question.reply" for v, _ in recorder.calls)
        resolved = replied and _wait_until_resolved(source, item.request_id)
        verdict_lines = _line_count(verdicts)
        return {
            "resolved": resolved,
            "request_id": item.request_id,
            "verdict_recorded": verdict_lines == 1,
        }
    finally:
        _cmux("close-workspace", "--workspace", ws)


def writes_verdict_live_smoke(tmp_dir: str = "/tmp/atdd-feed-daemon-verdict") -> dict:
    """M003 — a live daemon WRITES A VERDICT for a real induced safe decision.

    The headline gate the L007 inclusion smoke missed (#1007). Drive the REAL decide
    path — the production workspace-scoped ``CmuxFeedSource``, the real ``LlmCoach``
    over ``claude -p`` (whose factory now forces ``stdin=DEVNULL``, the detached
    daemon's no-TTY condition), and the durable ``JsonlVerdictLedger`` — over one
    tick against a live worker blocked on a real AskUserQuestion. Assert
    ``verdicts.jsonl`` GAINS A LINE: the daemon completed a real decision and recorded
    it, rather than the silent zero-verdicts failure. Captures evidence (#983).
    """
    tmp = Path(tmp_dir)
    tmp.mkdir(parents=True, exist_ok=True)
    verdicts, escalations = tmp / "verdicts.jsonl", tmp / "escalations.jsonl"
    for ledger in (verdicts, escalations):
        if ledger.exists():
            ledger.unlink()
    ws, worker = _spawn_claude_worker("atdd-feed-1007-verdict")
    try:
        _send_task(ws, worker, _QUESTION_TASK)
        # Production scoped read (the #993/#1004 path) — the daemon's real source.
        source = CmuxFeedSource(workspace_id=ws)
        item = _wait_for_pending(source, kind=QUESTION)
        assert item is not None, "no pending question item appeared in the scoped Feed"

        recorder = _RecordingTransport(CmuxFeedTransport())
        daemon = _build_live_daemon(
            source=source, coach=LlmCoach(), recorder=recorder,
            verdicts=verdicts, escalations=escalations,
        )
        daemon.tick()

        verdict_lines = _line_count(verdicts)
        return {
            "verdict_written": verdict_lines >= 1,
            "verdict_lines": verdict_lines,
            "request_id": item.request_id,
            "escalation_lines": _line_count(escalations),
            "replied": any(v == "feed.question.reply" for v, _ in recorder.calls),
        }
    finally:
        _cmux("close-workspace", "--workspace", ws)


def danger_escalates_live_smoke(tmp_dir: str = "/tmp/atdd-feed-daemon-danger") -> dict:
    """C004 — a real dangerous tool use is escalated, never auto-answered.

    THE critical safety smoke: the dangerous permission must be recorded to the
    escalations ledger AND loud-logged, with NO Feed reply and the coach NEVER
    consulted (the spy coach proves the gate runs ahead of any LLM call).
    """
    tmp = Path(tmp_dir)
    tmp.mkdir(parents=True, exist_ok=True)
    verdicts, escalations = tmp / "verdicts.jsonl", tmp / "escalations.jsonl"
    ws, worker = _spawn_claude_worker("atdd-feed-966-danger")
    handler = _ListHandler()
    logger = logging.getLogger("atdd.feed_daemon")
    logger.addHandler(handler)
    try:
        _send_task(ws, worker, _DANGER_TASK)
        source = CmuxFeedSource()
        item = _wait_for_pending(
            source, kind=PERMISSION,
            predicate=lambda i: match_danger(i.tool_input or "") is not None,
        )
        if item is None:
            raise PermissionNotInducible(
                "no blocked dangerous permission appeared in the Feed under cmux auto-mode"
            )

        recorder = _RecordingTransport(CmuxFeedTransport())
        spy = _SpyCoach(LlmCoach())
        daemon = _build_live_daemon(
            source=source, coach=spy, recorder=recorder,
            verdicts=verdicts, escalations=escalations,
        )
        outcomes = daemon.tick()

        escalated = next(
            (o for o in outcomes if o.request_id == item.request_id and o.escalation),
            None,
        )
        assert escalated is not None, "dangerous item was not escalated"
        return {
            "cause": escalated.escalation.cause,
            "auto_replied": bool(recorder.calls),          # MUST be False
            "coach_consulted": bool(spy.calls),            # MUST be False
            "escalation_recorded": _line_count(escalations) >= 1,
            "loud_logged": any(r.levelno >= logging.WARNING for r in handler.records),
        }
    finally:
        logger.removeHandler(handler)
        _cmux("close-workspace", "--workspace", ws)


def restart_no_double_answer_live_smoke(
    tmp_dir: str = "/tmp/atdd-feed-daemon-restart",
) -> dict:
    """E005 — a restarted daemon re-escalates nothing for an already-handled item.

    Uses the dangerous item because it STAYS blocked (it is never auto-answered),
    so it is genuinely re-presented to the second daemon — whose re-hydrated
    answered-set must skip it: no new escalation line, no reply, coach untouched.
    """
    tmp = Path(tmp_dir)
    tmp.mkdir(parents=True, exist_ok=True)
    verdicts, escalations = tmp / "verdicts.jsonl", tmp / "escalations.jsonl"
    ws, worker = _spawn_claude_worker("atdd-feed-966-restart")
    try:
        _send_task(ws, worker, _DANGER_TASK)
        source = CmuxFeedSource()
        item = _wait_for_pending(
            source, kind=PERMISSION,
            predicate=lambda i: match_danger(i.tool_input or "") is not None,
        )
        if item is None:
            raise PermissionNotInducible(
                "no blocked dangerous permission appeared in the Feed under cmux auto-mode"
            )

        # daemon #1 — escalates the dangerous item, writes escalations.jsonl
        rec1 = _RecordingTransport(CmuxFeedTransport())
        daemon1 = _build_live_daemon(
            source=source, coach=_SpyCoach(LlmCoach()), recorder=rec1,
            verdicts=verdicts, escalations=escalations,
        )
        daemon1.tick()
        before = _line_count(escalations)

        # daemon #2 — fresh process would re-hydrate from the SAME ledgers
        spy2 = _SpyCoach(LlmCoach())
        rec2 = _RecordingTransport(CmuxFeedTransport())
        daemon2 = _build_live_daemon(
            source=source, coach=spy2, recorder=rec2,
            verdicts=verdicts, escalations=escalations,
        )
        daemon2.tick()
        after = _line_count(escalations)

        return {
            "re_answered": bool(rec2.calls) or bool(spy2.calls) or after != before,
            "escalation_lines_before": before,
            "escalation_lines_after": after,
        }
    finally:
        _cmux("close-workspace", "--workspace", ws)


# --------------------------------------------------------------------------- #
# Process-level smokes (no cmux/claude needed; safe to run anywhere)           #
# --------------------------------------------------------------------------- #
_DAEMON_PROC = """
import sys
from pathlib import Path
from atdd.mediate_worker_decisions.feed_daemon.composition import build_feed_daemon
from atdd.mediate_worker_decisions.feed_daemon.src.domain.answered_set import AnsweredSet
from atdd.mediate_worker_decisions.feed_daemon.src.integration.jsonl_ledgers import (
    JsonlEscalationSink, JsonlVerdictLedger,
)
from atdd.mediate_worker_decisions.feed_daemon.src.integration.pidfile_lock import PidfileLock
from atdd.mediate_worker_decisions.feed_daemon.src.integration.signal_stop import (
    SignalStop, RealSleeper,
)
from atdd.mediate_worker_decisions.feed_daemon.src.application.feed_daemon import (
    SingleInstanceError,
)

lock_path = Path(sys.argv[1])
tmp = lock_path.parent

class _EmptySource:
    def list_pending(self):
        return []  # no Feed items: exercise lifecycle only

class _NoRunner:
    def handle(self, item):  # pragma: no cover - never reached
        raise AssertionError("runner must not be called with an empty Feed")

daemon = build_feed_daemon(
    source=_EmptySource(),
    runner=_NoRunner(),
    escalation_sink=JsonlEscalationSink(tmp / "escalations.jsonl"),
    verdict_ledger=JsonlVerdictLedger(tmp / "verdicts.jsonl"),
    sleeper=RealSleeper(),
    stop=SignalStop().install(),
    lock=PidfileLock(lock_path),
    answered=AnsweredSet(),
    poll_interval_s=0.2,
)
try:
    daemon.run_forever()
except SingleInstanceError:
    print("REFUSED", flush=True)
    sys.exit(3)
print("EXITED", flush=True)
sys.exit(0)
"""


def _spawn_daemon_proc(lock_path: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", _DAEMON_PROC, str(lock_path)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


def _wait_for_lock(lock_path: Path, timeout: float = _PROC_BOOT_TIMEOUT) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if lock_path.exists() and lock_path.read_text().strip():
            return True
        time.sleep(0.1)
    return False


def sigterm_clean_shutdown_live_smoke(tmp_dir: str = "/tmp/atdd-feed-daemon-term") -> dict:
    """R002 — a running daemon process exits cleanly and releases its lock on SIGTERM."""
    import signal

    tmp = Path(tmp_dir)
    tmp.mkdir(parents=True, exist_ok=True)
    lock_path = tmp / "feed-daemon.lock"
    if lock_path.exists():
        lock_path.unlink()

    proc = _spawn_daemon_proc(lock_path)
    try:
        acquired = _wait_for_lock(lock_path)
        assert acquired, "daemon never acquired its lock"
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=_PROC_EXIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise
        return {
            "exited_cleanly": proc.returncode == 0,
            "lock_released": not lock_path.exists(),
            "returncode": proc.returncode,
        }
    finally:
        if proc.poll() is None:
            proc.kill()


def second_instance_refused_live_smoke(tmp_dir: str = "/tmp/atdd-feed-daemon-single") -> dict:
    """D002 — a second daemon process refuses to start while the first holds the lock."""
    tmp = Path(tmp_dir)
    tmp.mkdir(parents=True, exist_ok=True)
    lock_path = tmp / "feed-daemon.lock"
    if lock_path.exists():
        lock_path.unlink()

    first = _spawn_daemon_proc(lock_path)
    try:
        assert _wait_for_lock(lock_path), "first daemon never acquired its lock"
        second = _spawn_daemon_proc(lock_path)
        out = second.communicate(timeout=_PROC_EXIT_TIMEOUT)[0]
        first_still_running = first.poll() is None
        return {
            "second_refused": second.returncode != 0 and "REFUSED" in (out or ""),
            "second_returncode": second.returncode,
            "first_still_holds_lock": first_still_running and lock_path.exists(),
        }
    finally:
        import signal

        if first.poll() is None:
            first.send_signal(signal.SIGTERM)
            try:
                first.wait(timeout=_PROC_EXIT_TIMEOUT)
            except subprocess.TimeoutExpired:
                first.kill()


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len([ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()])
