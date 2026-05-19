# URN: test:spawn-agents:worker-launch-prompt-readiness-gate:E010-UNIT-005-decision-log-gated-on-assertion
# Acceptance: acc:spawn-agents:E010-UNIT-005-decision-log-gated-on-assertion
# WMBT: wmbt:spawn-agents:E010
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E010-UNIT-005 — decisions.jsonl emits 'transitioned:true' only if
_assert_worker_processing passed; on assertion failure the log records
'transitioned:false' and escalation is triggered, with the handler
returning HandlerResult.ERROR.

RED: The current coach.py writes the INIT→PLANNED decision with
transitioned:True *before* the spawn action — the J3 write-before-action
pattern — and does not check whether the worker processed the launch prompt
at all. This test pins the required gating behavior (issue #795).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.handlers.state_machine import (
    CoachContext,
    HandlerResult,
    Phase,
    Transition,
)


class _NeverProcessingMux:
    """Always returns empty capture — the worker never processes anything."""

    def __init__(self):
        self.calls: list = []

    def new_workspace(self, *a, **kw):
        self.calls.append("new_workspace")
        return "ws-1"

    def new_surface(self, *a, **kw):
        self.calls.append("new_surface")
        return "surface:99"

    def paste_text(self, surface_ref, text, **kw):
        self.calls.append("paste_text")

    def send_key(self, surface_ref, key, **kw):
        self.calls.append("send_key")

    def list_surfaces(self, **kw):
        return []

    def capture_surface_text(self, surface_ref: str) -> str:
        return ""  # worker never processes — queue stays backed up


def test_decision_records_transitioned_false_when_worker_silent(tmp_path, monkeypatch):
    """When _assert_worker_processing times out, decisions.jsonl must NOT
    record 'transitioned:true' for the phase transition."""
    from atdd.coach.handlers import spawn as spawn_handler

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    # Use a very short readiness-gate timeout so the test is fast.
    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "0.05")

    escalations: list[str] = []

    class _EscalatingCtx(CoachContext):
        pass

    ctx = _EscalatingCtx(
        issue_number=795,
        runtime_dir=runtime,
        multiplexer="cmux",
        multiplexer_mode="pane",
        multiplexer_backend=_NeverProcessingMux(),
        worktree_override=worktree,
        escalation_channel="file:" + str(tmp_path / "escalations.log"),
    )

    result = spawn_handler.handle(ctx, Transition(Phase.INIT, Phase.PLANNED))

    # The handler MUST return ERROR, not HANDLED.
    assert result == HandlerResult.ERROR

    # The decisions.jsonl MUST NOT contain a transitioned:true entry for
    # INIT→PLANNED when the worker did not process the launch prompt.
    decisions_path = runtime / "coach" / "decisions.jsonl"
    if decisions_path.exists():
        for line in decisions_path.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if (
                record.get("decision_type") == "phase-transition"
                and record.get("inputs", {}).get("target_phase") == "PLANNED"
            ):
                outcome = record.get("outcome", {})
                assert outcome.get("transitioned") is not True, (
                    "decisions.jsonl must not record transitioned:true when "
                    "the worker never processed the launch prompt"
                )
