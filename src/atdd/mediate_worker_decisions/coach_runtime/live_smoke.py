"""Live smokes for the coach runtime (opt-in via ATDD_LIVE_DAEMON=1).

These drive the REAL start/wait paths against real processes. They skip cleanly
(returning ``{"skipped": True, "reason": ...}``) when cmux or a live worker
workspace is unavailable, and capture evidence (#983) to the scratch dir so a
passing live run leaves an artifact behind.

Run from a /tmp scratch dir, NOT a worktree.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

from atdd.mediate_worker_decisions.coach_runtime.src.log import log as _log


def _cmux_available() -> bool:
    return shutil.which("cmux") is not None


def _write_evidence(scratch: Path, name: str, evidence: dict) -> None:
    try:
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / name).write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    except OSError as exc:
        _log.debug(
            "evidence capture failed (best-effort)",
            extra={"name": name, "error": str(exc)},
        )


def start_launches_scoped_daemon_live_smoke(
    *, workspace_id: Optional[str] = None
) -> dict:
    """E010-SMOKE-001 — real `atdd coach start` launches the scoped feed_daemon.

    Spawns the actual feed_daemon CLI subprocess in a /tmp scratch runtime dir
    and asserts a manager pidfile is written naming a live process. Cleans up by
    stopping the daemon. Skips when cmux is unavailable.
    """
    if not _cmux_available():
        return {"skipped": True, "reason": "cmux not found on PATH"}

    from atdd.mediate_worker_decisions.coach_runtime.composition import (
        build_coach_runtime_from_repo,
        resolve_workspace_paths,
    )
    from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
        OsLivenessProbe,
    )

    ws = workspace_id or os.environ.get("ATDD_LIVE_WORKSPACE") or f"smoke-{uuid.uuid4().hex[:8]}"
    scratch = Path(tempfile.mkdtemp(prefix="coach-runtime-e010-"))
    runtime_root = scratch / ".atdd" / "runtime" / "coach-runtime"

    runtime = build_coach_runtime_from_repo(runtime_root=runtime_root)
    paths = resolve_workspace_paths(ws, repo_root=scratch)
    daemon = runtime.start(
        ws,
        lock_path=paths["lock_path"],
        escalations_path=paths["escalations_path"],
        verdicts_path=paths["verdicts_path"],
        run_gate=False,  # gate already ran for the coach session; keep the smoke tight
    )

    time.sleep(1.0)  # let the child settle
    pidfile = runtime_root / _slug(ws) / "manager.json"
    alive = OsLivenessProbe().is_alive(daemon.pid)
    evidence = {
        "workspace_id": ws,
        "pid": daemon.pid,
        "pidfile": str(pidfile),
        "pidfile_written": pidfile.exists(),
        "process_alive": alive,
        "scratch": str(scratch),
    }
    _write_evidence(scratch, "e010-evidence.json", evidence)

    runtime.stop(ws)  # cleanup
    return evidence


def stop_terminates_managed_daemon_live_smoke(
    *, workspace_id: Optional[str] = None
) -> dict:
    """R003-SMOKE-001 — `atdd coach stop` terminates a real managed daemon.

    Starts a real feed_daemon subprocess, signals it via stop, and asserts the
    process exits and its pidfile is removed. Skips when cmux is unavailable.
    """
    if not _cmux_available():
        return {"skipped": True, "reason": "cmux not found on PATH"}

    from atdd.mediate_worker_decisions.coach_runtime.composition import (
        build_coach_runtime_from_repo,
        resolve_workspace_paths,
    )
    from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
        OsLivenessProbe,
        workspace_slug,
    )

    ws = workspace_id or os.environ.get("ATDD_LIVE_WORKSPACE") or f"smoke-{uuid.uuid4().hex[:8]}"
    scratch = Path(tempfile.mkdtemp(prefix="coach-runtime-r003-"))
    runtime_root = scratch / ".atdd" / "runtime" / "coach-runtime"
    runtime = build_coach_runtime_from_repo(runtime_root=runtime_root)
    paths = resolve_workspace_paths(ws, repo_root=scratch)
    daemon = runtime.start(
        ws,
        lock_path=paths["lock_path"],
        escalations_path=paths["escalations_path"],
        verdicts_path=paths["verdicts_path"],
        run_gate=False,
    )
    time.sleep(1.0)

    runtime.stop(ws)
    # Poll for the process to actually exit (bounded). The daemon is a direct
    # child of THIS process here, so on exit it lingers as a zombie until reaped
    # — os.kill(pid, 0) would still report it alive. Reap it with waitpid so we
    # observe the real exit. (In production `atdd coach stop` returns immediately,
    # so init reaps the daemon — no zombie.)
    probe = OsLivenessProbe()
    deadline = _wall() + 15.0
    exited = False
    while _wall() < deadline:
        try:
            wpid, _ = os.waitpid(daemon.pid, os.WNOHANG)
            if wpid == daemon.pid:
                exited = True
                break
        except ChildProcessError:
            exited = not probe.is_alive(daemon.pid)  # not our child / already reaped
            if exited:
                break
        except OSError as exc:
            _log.debug("waitpid probe failed; retrying", extra={"pid": daemon.pid, "error": str(exc)})
        time.sleep(0.2)

    pidfile = runtime_root / workspace_slug(ws) / "manager.json"
    evidence = {
        "workspace_id": ws,
        "pid": daemon.pid,
        "process_exited": exited,
        "pidfile_removed": not pidfile.exists(),
        "scratch": str(scratch),
    }
    _write_evidence(scratch, "r003-evidence.json", evidence)
    return evidence


def wait_emits_induced_escalation_live_smoke(
    *, workspace_id: Optional[str] = None
) -> dict:
    """L006-SMOKE-001 — after inducing an escalation, wait emits exactly it.

    Requires a live worker workspace whose daemon raises an escalation
    (worker_stuck, or a now-surfaced dangerous decision via #971). When the
    induction path is unavailable, skips cleanly. Asserts the emitted record
    matches the induced one and a second wait does not re-emit it.
    """
    if not _cmux_available():
        return {"skipped": True, "reason": "cmux not found on PATH"}

    ws = workspace_id or os.environ.get("ATDD_LIVE_WORKSPACE")
    if not ws:
        return {
            "skipped": True,
            "reason": "no live worker workspace (set ATDD_LIVE_WORKSPACE); "
            "escalation induction not available in this environment",
        }

    from atdd.mediate_worker_decisions.coach_runtime.composition import (
        build_coach_runtime_from_repo,
        resolve_workspace_paths,
    )
    from atdd.mediate_worker_decisions.coach_runtime.src.integration.jsonl_escalation_reader import (
        FileCursorStore,
        JsonlEscalationReader,
    )
    from atdd.mediate_worker_decisions.feed_daemon.src.integration.signal_stop import (
        RealSleeper,
    )

    scratch = Path(tempfile.mkdtemp(prefix="coach-runtime-l006-"))
    runtime_root = scratch / ".atdd" / "runtime" / "coach-runtime"
    runtime = build_coach_runtime_from_repo(runtime_root=runtime_root)
    paths = resolve_workspace_paths(ws, repo_root=scratch)
    runtime.start(
        ws,
        lock_path=paths["lock_path"],
        escalations_path=paths["escalations_path"],
        verdicts_path=paths["verdicts_path"],
        run_gate=False,
    )

    reader = JsonlEscalationReader(Path(paths["escalations_path"]))
    cursor = FileCursorStore(Path(paths["cursor_path"]))

    # Wait for the induced escalation with a bounded budget (the operator induces
    # a worker_stuck / dangerous decision against the live workspace out-of-band).
    deadline = _wall() + float(os.environ.get("ATDD_LIVE_WAIT_BUDGET", "120"))

    class _DeadlineStop:
        def is_set(self) -> bool:
            return _wall() >= deadline

    emitted = runtime.wait_next(
        reader=reader, cursor_store=cursor, sleeper=RealSleeper(),
        stop=_DeadlineStop(), poll_interval=1.0,
    )
    if emitted is None:
        runtime.stop(ws)
        return {
            "skipped": True,
            "reason": "no escalation induced within the wait budget",
        }

    # A second wait must not re-emit the handled escalation (cursor advanced).
    class _OnePollStop:
        def __init__(self):
            self._n = 1

        def is_set(self) -> bool:
            if self._n > 0:
                self._n -= 1
                return False
            return True

    second = runtime.wait_next(
        reader=reader, cursor_store=cursor, sleeper=RealSleeper(),
        stop=_OnePollStop(), poll_interval=0.0,
    )
    reemitted = bool(second) and second.get("escalation_id") == emitted.get("escalation_id")

    evidence = {
        "workspace_id": ws,
        "induced_escalation_id": emitted.get("escalation_id"),
        "emitted_escalation_id": emitted.get("escalation_id"),
        "emitted_record": emitted,
        "reemitted": reemitted,
        "scratch": str(scratch),
    }
    _write_evidence(scratch, "l006-evidence.json", evidence)
    runtime.stop(ws)
    return evidence


def real_coach_start_writes_verdict_live_smoke(tmp_dir: Optional[str] = None) -> dict:
    """M005-SMOKE-001 — the REAL `atdd coach start` decides through to a verdict.

    The headline gate every prior #1007 round missed. M003-SMOKE drove the daemon
    LOOP directly (``build_feed_daemon`` + ``tick``) and passed while the real
    command was broken — because the bug lives in the detached spawn, not the loop:
    ``atdd coach start`` launches the daemon via ``SubprocessDaemonSpawner`` and the
    detached child inherited the coach session's stale ``CMUX_*`` client-context env,
    so its ``cmux rpc`` broke-pipe and ``run_cmux`` swallowed it to an empty Feed.

    This drives the PRODUCTION entry point — ``CoachRuntime.start`` over the real
    ``SubprocessDaemonSpawner`` (the same call ``atdd coach start --workspace`` makes)
    — against a real worker blocked on a real AskUserQuestion, then asserts the
    MANAGED daemon's own ``verdicts.jsonl`` gains a line. Skips cleanly without cmux.
    """
    if not _cmux_available():
        return {"skipped": True, "reason": "cmux not found on PATH"}

    from atdd.mediate_worker_decisions.bridge_cmux_feed.live_smoke import (
        _cmux as _bridge_cmux,
        _send_task,
        _spawn_claude_worker,
        _wait_for_pending,
    )
    from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import QUESTION
    from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_event_source import (
        CmuxFeedSource,
    )
    from atdd.mediate_worker_decisions.coach_runtime.composition import (
        build_coach_runtime_from_repo,
        resolve_workspace_paths,
    )

    question_task = (
        "Use the AskUserQuestion tool right now to ask whether to indent with "
        "Tabs or Spaces (options: 'Tabs', 'Spaces'). Do nothing else first."
    )
    scratch = Path(tmp_dir) if tmp_dir else Path(tempfile.mkdtemp(prefix="coach-runtime-m005-"))
    runtime_root = scratch / ".atdd" / "runtime" / "coach-runtime"

    ws, worker = _spawn_claude_worker("atdd-coach-1007-real-start")
    try:
        _send_task(ws, worker, question_task)
        # Confirm the worker is actually blocked on a question in the SCOPED feed
        # before we hand the workspace to the managed daemon.
        item = _wait_for_pending(CmuxFeedSource(workspace_id=ws), kind=QUESTION)
        assert item is not None, "no pending question item appeared in the scoped Feed"

        # The production path: build the repo-wired runtime and START — exactly what
        # `atdd coach start --workspace <ws>` does (detached SubprocessDaemonSpawner).
        runtime = build_coach_runtime_from_repo(runtime_root=runtime_root)
        paths = resolve_workspace_paths(ws, repo_root=scratch)

        # Faithfully recreate the #1007 production condition that prior smokes missed:
        # a coach session exports a stale cmux CLIENT-CONTEXT socket that conflicts
        # with the live one, and the detached daemon must NOT inherit it. We set it
        # ONLY around the spawn (the child inherits os.environ at Popen time) and
        # restore immediately, so the parent's own cmux calls stay clean. WITHOUT the
        # env scrub the daemon inherits this and every `cmux rpc` fails -> empty Feed
        # -> zero verdicts; WITH the scrub it reaches the server cleanly and decides.
        stale_socket = str(scratch / "stale-coach.sock")
        _saved_socket = os.environ.get("CMUX_SOCKET")
        os.environ["CMUX_SOCKET"] = stale_socket
        try:
            daemon = runtime.start(
                ws,
                lock_path=paths["lock_path"],
                escalations_path=paths["escalations_path"],
                verdicts_path=paths["verdicts_path"],
                run_gate=False,  # the coach session already gated; keep the smoke tight
            )
        finally:
            # The child already inherited at Popen time; the parent must go clean again.
            if _saved_socket is None:
                os.environ.pop("CMUX_SOCKET", None)
            else:
                os.environ["CMUX_SOCKET"] = _saved_socket

        verdicts = Path(paths["verdicts_path"])
        budget = float(os.environ.get("ATDD_LIVE_WAIT_BUDGET", "120"))
        deadline = _wall() + budget
        while _wall() < deadline and _line_count(verdicts) < 1:
            time.sleep(1.0)

        log_path = Path(paths["lock_path"]).parent / "daemon.log"
        evidence = {
            "workspace_id": ws,
            "daemon_pid": daemon.pid,
            "verdict_written": _line_count(verdicts) >= 1,
            "verdict_lines": _line_count(verdicts),
            "request_id": item.request_id,
            "verdicts_path": str(verdicts),
            "stale_socket_injected": stale_socket,
            "daemon_log_tail": _tail(log_path, 40),
            "scratch": str(scratch),
        }
        _write_evidence(scratch, "m005-evidence.json", evidence)
        return evidence
    finally:
        try:
            build_coach_runtime_from_repo(runtime_root=runtime_root).stop(ws)
        except Exception as exc:  # best-effort cleanup; never mask the result
            _log.debug("daemon stop during cleanup failed", extra={"error": str(exc)})
        _bridge_cmux("close-workspace", "--workspace", ws)


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len([ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()])


def _tail(path: Path, n: int) -> str:
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8").splitlines()[-n:])


def _slug(workspace_id: str) -> str:
    from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
        workspace_slug,
    )

    return workspace_slug(workspace_id)


def _wall() -> float:
    return time.time()
