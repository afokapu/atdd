# URN: test:spawn-agents:worker-launch-prompt-readiness-gate:E010-UNIT-005-decision-log-gated-on-assertion
# Acceptance: acc:spawn-agents:E010-UNIT-005-decision-log-gated-on-assertion
# WMBT: wmbt:spawn-agents:E010
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E010-UNIT-005 — decisions.jsonl emits 'transitioned:true' only if
_assert_worker_processing passed; on assertion failure (jsonl never grows)
the handler returns HandlerResult.ERROR and no phantom transitioned:true is
recorded.

RED: The test now sets up ATDD_CLAUDE_PROJECTS_DIR with a static jsonl so
_wait_for_claude_ready passes but _assert_worker_processing times out. With
the old capture_surface_text implementation the short timeout fires through
a different code path (capture_surface_text returns ""), but the desired
outcome (HandlerResult.ERROR, no transitioned:true) is identical. The new
path is verified when GREEN lands.
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


class _MinimalMux:
    """Minimal fake that satisfies surface-creation without capture_surface_text."""

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


def test_decision_records_transitioned_false_when_worker_silent(tmp_path, monkeypatch):
    """When the worker never processes (jsonl static), decisions.jsonl must NOT
    record 'transitioned:true' for the phase transition."""
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.utils.session_naming_apply import _claude_project_key

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    # Set up a static project dir so _wait_for_claude_ready passes but
    # _assert_worker_processing times out (no new bytes are ever appended).
    claude_projects = tmp_path / ".claude" / "projects"
    claude_projects.mkdir(parents=True)
    monkeypatch.setenv("ATDD_CLAUDE_PROJECTS_DIR", str(claude_projects))

    project_key = _claude_project_key(worktree)
    project_dir = claude_projects / project_key
    project_dir.mkdir(parents=True)
    (project_dir / "session.jsonl").write_text("{}\n")  # static — never grows

    # Short timeout so the test is fast.
    monkeypatch.setenv("ATDD_WORKER_READY_TIMEOUT", "0.1")
    monkeypatch.setenv("ATDD_WORKER_POLL_INTERVAL", "0.01")

    ctx = CoachContext(
        issue_number=795,
        runtime_dir=runtime,
        multiplexer="cmux",
        multiplexer_mode="pane",
        multiplexer_backend=_MinimalMux(),
        worktree_override=worktree,
        escalation_channel="file:" + str(tmp_path / "escalations.log"),
    )

    result = spawn_handler.handle(ctx, Transition(Phase.INIT, Phase.PLANNED))

    # The handler MUST return ERROR, not HANDLED.
    assert result == HandlerResult.ERROR

    # decisions.jsonl must NOT contain a transitioned:true entry for INIT→PLANNED.
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
