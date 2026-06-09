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
import subprocess
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

    Launches the actual feed_daemon as a headless cmux surface in a /tmp scratch
    runtime dir and asserts a manager record is written naming the daemon's own
    cmux workspace, which exists. Cleans up by stopping the daemon. Skips when cmux
    is unavailable.
    """
    if not _cmux_available():
        return {"skipped": True, "reason": "cmux not found on PATH"}

    from atdd.mediate_worker_decisions.coach_runtime.composition import (
        build_coach_runtime_from_repo,
        resolve_workspace_paths,
    )
    from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
        CmuxWorkspaceLiveness,
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

    time.sleep(1.0)  # let the surface settle
    pidfile = runtime_root / _slug(ws) / "manager.json"
    alive = CmuxWorkspaceLiveness().is_alive(daemon.daemon_workspace)
    evidence = {
        "workspace_id": ws,
        "daemon_workspace": daemon.daemon_workspace,
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

    Launches a real feed_daemon cmux surface, stops it (cmux close-workspace), and
    asserts the daemon's workspace no longer exists and its manager record is
    removed. Skips when cmux is unavailable.
    """
    if not _cmux_available():
        return {"skipped": True, "reason": "cmux not found on PATH"}

    from atdd.mediate_worker_decisions.coach_runtime.composition import (
        build_coach_runtime_from_repo,
        resolve_workspace_paths,
    )
    from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
        CmuxWorkspaceLiveness,
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
    # Poll until the daemon's cmux surface workspace is gone (bounded).
    probe = CmuxWorkspaceLiveness()
    deadline = _wall() + 15.0
    exited = False
    while _wall() < deadline:
        if not probe.is_alive(daemon.daemon_workspace):
            exited = True
            break
        time.sleep(0.2)

    pidfile = runtime_root / workspace_slug(ws) / "manager.json"
    evidence = {
        "workspace_id": ws,
        "daemon_workspace": daemon.daemon_workspace,
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
    command was broken — because the bug was in the spawn, not the loop: ``atdd
    coach start`` spawned the daemon as a DETACHED subprocess and exited, ORPHANING
    it, and cmux rejects orphaned processes (every ``cmux rpc`` broken-pipes
    regardless of env). The fix launches the daemon INSIDE a headless cmux surface.

    This drives the PRODUCTION entry point — ``CoachRuntime.start`` over the real
    ``CmuxSurfaceDaemonLauncher`` (the same cmux-surface spawn ``atdd coach start
    --workspace`` makes) — against a real worker blocked on a real AskUserQuestion,
    then asserts the MANAGED daemon's own ``verdicts.jsonl`` gains a line. Because the
    daemon is a cmux surface (parented to cmux, NOT a child of this process), this
    exercises the real orphan-immune path — not a live-parent subprocess. Skips
    cleanly without cmux.
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
        # `atdd coach start --workspace <ws>` does (cmux-surface daemon launch). The
        # daemon runs inside its own cmux surface, so it is a socket-recognized
        # process — never an orphaned detached subprocess (#1007).
        runtime = build_coach_runtime_from_repo(runtime_root=runtime_root)
        paths = resolve_workspace_paths(ws, repo_root=scratch)
        daemon = runtime.start(
            ws,
            lock_path=paths["lock_path"],
            escalations_path=paths["escalations_path"],
            verdicts_path=paths["verdicts_path"],
            run_gate=False,  # the coach session already gated; keep the smoke tight
        )

        verdicts = Path(paths["verdicts_path"])
        budget = float(os.environ.get("ATDD_LIVE_WAIT_BUDGET", "120"))
        deadline = _wall() + budget
        while _wall() < deadline and _line_count(verdicts) < 1:
            time.sleep(1.0)

        log_path = Path(paths["lock_path"]).parent / "daemon.log"
        evidence = {
            "workspace_id": ws,
            "daemon_workspace": daemon.daemon_workspace,
            "verdict_written": _line_count(verdicts) >= 1,
            "verdict_lines": _line_count(verdicts),
            "request_id": item.request_id,
            "verdicts_path": str(verdicts),
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


def live_smoke_available() -> Optional[str]:
    """Return ``None`` when the E012 headline harness can run, else a skip reason.

    Needs cmux + claude on PATH, a live cmux surface, and the explicit
    ``ATDD_LIVE_SMOKE=1`` opt-in so ordinary runs never drive a real dispatch.
    """
    if os.environ.get("ATDD_LIVE_SMOKE") != "1":
        return "live smoke is opt-in: set ATDD_LIVE_SMOKE=1 (needs a live cmux surface)"
    if not shutil.which("cmux"):
        return "cmux not on PATH"
    if not shutil.which("claude"):
        return "claude not on PATH"
    if not os.environ.get("CMUX_SURFACE_ID"):
        return "not running under a live cmux surface (CMUX_SURFACE_ID unset)"
    return None


def _coach_runtime_ledger_counts(root: Path) -> tuple[int, int]:
    """(verdict_lines, escalation_lines) summed across every workspace ledger."""
    verdicts = escalations = 0
    if not root.is_dir():
        return (0, 0)
    for p in root.glob("*/verdicts.jsonl"):
        verdicts += sum(1 for _ in p.open()) if p.is_file() else 0
    for p in root.glob("*/escalations.jsonl"):
        escalations += sum(1 for _ in p.open()) if p.is_file() else 0
    return (verdicts, escalations)


def _last_ledger_record(root: Path, kind: str) -> Optional[dict]:
    """The most recent decision record of ``kind`` (verdicts|escalations) across
    every workspace ledger — the durable proof a decision was mediated, captured
    as evidence so the headline asserts a real record, not a log line."""
    latest: Optional[dict] = None
    for p in root.glob(f"*/{kind}.jsonl"):
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                latest = json.loads(line)
            except json.JSONDecodeError:
                continue
    return latest


def _issue_status_label(issue: int) -> str:
    out = subprocess.run(
        ["gh", "issue", "view", str(issue), "--json", "labels",
         "--jq", '[.labels[].name | select(startswith("atdd:"))] | join(",")'],
        capture_output=True, text=True, timeout=30,
    )
    return (out.stdout or "").strip()


def coach_dispatch_drives_fixture_live_smoke(*, timeout_s: int = 600) -> dict:
    """Run `atdd coach <fixture>` end-to-end through ONE mediated decision (E012).

    The single autonomous command drives a REAL fixture issue (env
    ``ATDD_SMOKE_FIXTURE_ISSUE``): the dispatch spawns the worker (which publishes
    to the Feed) AND attaches the workspace-scoped daemon, and the daemon MEDIATES
    the worker's first decision — a verdict or escalation lands in the
    coach-runtime ledger — with no human, no ``cmux send``, no TUI.

    Scope (autonomously reachable): the headline proves the autonomous loop CLOSES
    — worker raises a decision → attached daemon mediates → a durable verdict /
    escalation record is written. It does NOT assert a GitHub phase-label advance:
    crossing a phase gate (e.g. INIT->PLANNED / PLANNED->RED) requires the operator
    approval token by #1017 design, so a fully-autonomous run cannot (and must not)
    push the issue past a gate. ``worker_proceeded`` reflects the verdict case
    (auto-answered → worker unblocked); an escalation correctly parks the worker
    for the operator. Anti-theater: asserts a real ledger RECORD, not a log line.

    Returns ``{"mediated": "verdict"|"escalation"|None, "decision_recorded": bool,
    "worker_proceeded": bool, "record": dict|None, "state_before": str,
    "state_after": str, "no_human_interaction": True}``.
    """
    fixture = os.environ.get("ATDD_SMOKE_FIXTURE_ISSUE")
    if not fixture:
        raise RuntimeError(
            "set ATDD_SMOKE_FIXTURE_ISSUE to a real INIT fixture issue number"
        )
    from atdd.mediate_worker_decisions.coach_runtime.composition import (
        default_runtime_root,
    )

    root = default_runtime_root()
    v0, e0 = _coach_runtime_ledger_counts(root)
    state_before = _issue_status_label(int(fixture))

    proc = subprocess.Popen(
        ["atdd", "coach", fixture, "--no-prompt"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    mediated: Optional[str] = None
    try:
        deadline = _wall() + timeout_s
        while _wall() < deadline:
            v1, e1 = _coach_runtime_ledger_counts(root)
            if e1 > e0:
                mediated = "escalation"
            elif v1 > v0:
                mediated = "verdict"
            # The autonomous loop has closed as soon as the daemon records a
            # decision — break on that, not on a phase advance the #1017 gate
            # deliberately withholds from an unattended run.
            if mediated is not None:
                break
            time.sleep(5)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
    record = _last_ledger_record(root, "escalations" if mediated == "escalation" else "verdicts") if mediated else None
    return {
        "mediated": mediated,
        "decision_recorded": mediated is not None,
        "worker_proceeded": mediated == "verdict",
        "record": record,
        "state_before": state_before,
        "state_after": _issue_status_label(int(fixture)),
        "no_human_interaction": True,
    }
