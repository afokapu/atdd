"""Live-cmux smoke harness for wagon:mediate-worker-decisions.

Drives the REAL bridge against a REAL throwaway cmux workspace (no synthetic
fixtures): it creates a worker surface that prints a decision prompt, runs
sense -> mediate -> apply, and observes the worker react. Always closes the
workspace it creates.

Used by the SMOKE tests, which run this when ``cmux`` is on PATH and skip
otherwise (e.g. CI runners without cmux). It needs no interactive focus — a
``--command`` workspace initializes a real terminal PTY headlessly.
"""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import List

from atdd.mediate_worker_decisions.apply_decision.composition import build_apply_use_case
from atdd.mediate_worker_decisions.apply_decision.src.integration.agent_control_applier import (
    InMemoryAppliedGuard,
)
from atdd.mediate_worker_decisions.apply_decision.src.integration.cmux_send_applier import (
    CmuxSendApplier,
)
from atdd.mediate_worker_decisions.mediate_decision.composition import build_mediate_use_case
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    CAUSE_DANGEROUS,
    Escalation,
    Verdict,
)
from atdd.mediate_worker_decisions.mediate_decision.src.integration.cmux_coach_client import (
    CmuxCoachClient,
    SystemClock,
)
from atdd.mediate_worker_decisions.sense_decision.composition import build_sense_use_case
from atdd.mediate_worker_decisions.sense_decision.src.application.sense_use_case import (
    SOURCE_NOTIFICATION,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import WorkerRef
from atdd.mediate_worker_decisions.sense_decision.src.integration.cmux_surface_reader import (
    CmuxSurfaceReader,
)


def _cmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["cmux", *args], capture_output=True, text=True, timeout=30)


def _surfaces(ws: str) -> List[str]:
    return re.findall(r"surface:\d+", _cmux("tree", "--workspace", ws).stdout)


class _StaticRegistry:
    def __init__(self, surface_id: str) -> None:
        self._sid = surface_id

    def resolve(self, surface_id: str):
        return WorkerRef(surface_id=surface_id) if surface_id == self._sid else None


class _Collector:
    def __init__(self) -> None:
        self.items: list = []

    def emit(self, item) -> None:
        self.items.append(item)

    def record(self, item) -> None:  # DecisionLedger port
        self.items.append(item)


def _make_workspace(name: str, prompt_lines: List[str]) -> tuple:
    script = Path("/tmp/atdd_smoke_worker_955.sh")
    body = "".join(f'echo "{ln}"\n' for ln in prompt_lines)
    script.write_text(body + "read ans\necho \"WORKER_GOT:$ans\"\nsleep 120\n")
    created = _cmux("new-workspace", "--name", name, "--cwd", ".",
                    "--command", f"bash {script}", "--focus", "false")
    ws = next((t for t in created.stdout.split() if t.startswith("workspace:")), None)
    if ws is None:
        raise RuntimeError(f"could not create cmux workspace: {created.stderr}")
    time.sleep(3.0)
    worker = _surfaces(ws)[0]
    _cmux("new-surface", "--type", "terminal", "--workspace", ws, "--focus", "false")
    time.sleep(1.5)
    coach = next(s for s in _surfaces(ws) if s != worker)
    return ws, worker, coach


def close_the_loop_smoke() -> dict:
    """sense -> mediate -> apply -> worker reacts. Raises AssertionError on failure."""
    ws, worker, coach = _make_workspace(
        "atdd-smoke-955-loop",
        ["Proceed with the migration?", "1) Apply", "2) Abort"],
    )
    try:
        req = build_sense_use_case(
            reader=CmuxSurfaceReader(ws), registry=_StaticRegistry(worker),
            sink=_Collector(),
        ).sense(surface_id=worker, source=SOURCE_NOTIFICATION)
        assert req is not None, "sense produced no request from the live worker surface"

        # pre-place the coach's structured reply, then run the dialogue
        _cmux("send", "--workspace", ws, "--surface", coach, "DECISION: 1")
        _cmux("send-key", "--workspace", ws, "--surface", coach, "Enter")
        _cmux("send", "--workspace", ws, "--surface", coach, "REASON: safe")
        _cmux("send-key", "--workspace", ws, "--surface", coach, "Enter")
        time.sleep(1.0)
        verdict = build_mediate_use_case(
            coach=CmuxCoachClient(ws, coach), clock=SystemClock(),
            verdict_sink=_Collector(), escalation_sink=_Collector(),
            timeout_seconds=8.0, poll_interval=1.0,
        ).handle(req)
        assert isinstance(verdict, Verdict) and verdict.selected_option_id == "1", verdict

        ledger = _Collector()
        record = build_apply_use_case(
            applier=CmuxSendApplier(ws), ledger=ledger, guard=InMemoryAppliedGuard(),
        ).apply(req, verdict)
        assert record.disposition == "applied", record.disposition

        time.sleep(1.5)
        worker_text = CmuxSurfaceReader(ws).read(worker)
        assert "WORKER_GOT:1" in worker_text, "worker did not receive the answer"
        return {"question": req.prompt.question, "selected": verdict.selected_option_id,
                "disposition": record.disposition, "drift_resolved": True}
    finally:
        _cmux("close-workspace", "--workspace", ws)


def danger_escalation_smoke() -> dict:
    """A dangerous prompt escalates and the coach is never contacted."""
    ws, worker, coach = _make_workspace(
        "atdd-smoke-955-danger",
        ["Apply the pending change?", "1) git push to origin main", "2) Abort"],
    )
    try:
        req = build_sense_use_case(
            reader=CmuxSurfaceReader(ws), registry=_StaticRegistry(worker),
            sink=_Collector(),
        ).sense(surface_id=worker, source=SOURCE_NOTIFICATION)
        assert req is not None, "sense produced no request from the live worker surface"
        outcome = build_mediate_use_case(
            coach=CmuxCoachClient(ws, coach), clock=SystemClock(),
            verdict_sink=_Collector(), escalation_sink=_Collector(),
            timeout_seconds=8.0, poll_interval=1.0,
        ).handle(req)
        assert isinstance(outcome, Escalation) and outcome.cause == CAUSE_DANGEROUS, outcome
        coach_text = CmuxSurfaceReader(ws).read(coach)
        assert "ATDD COACH DECISION REQUEST" not in coach_text, "coach was contacted!"
        return {"cause": outcome.cause, "coach_contacted": False}
    finally:
        _cmux("close-workspace", "--workspace", ws)
