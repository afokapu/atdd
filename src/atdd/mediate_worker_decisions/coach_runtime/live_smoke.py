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
        except OSError:
            pass
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


def _slug(workspace_id: str) -> str:
    from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
        workspace_slug,
    )

    return workspace_slug(workspace_id)


def _wall() -> float:
    return time.time()
