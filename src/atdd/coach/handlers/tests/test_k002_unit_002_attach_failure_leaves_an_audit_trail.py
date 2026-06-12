# URN: test:mediate-worker-decisions:feed-daemon-durability:K002-UNIT-002-attach-failure-leaves-an-audit-trail
# Acceptance: acc:mediate-worker-decisions:K002-UNIT-002-attach-failure-leaves-an-audit-trail
# WMBT: wmbt:mediate-worker-decisions:K002
# Phase: RED
# Layer: application
# Assertion: behavioral
"""K002-UNIT-002 — the attach-failure BLOCKED record identifies the worker + cause.

The durable trail left by an attach failure must be actionable: the BLOCKED
decision names the worker's surface and the attach-failure cause so an operator
can find and recover the unmediated worker.

RED: today no BLOCKED record is written on attach failure at all, so there is no
trail to inspect. Fails until the BLOCK-on-attach-failure behaviour lands.
"""
from __future__ import annotations

import json

import pytest

from atdd.coach.handlers.state_machine import (
    CoachContext,
    HandlerResult,
    Phase,
    Transition,
)

pytestmark = [pytest.mark.platform]

_ATTACH_MOD = (
    "atdd.mediate_worker_decisions.coach_runtime.src.presentation."
    "attach_worker_daemon"
)


def test_attach_failure_records_surface_and_cause(tmp_path, monkeypatch):
    from atdd.coach.handlers import spawn as spawn_handler

    runtime_root = tmp_path / ".atdd" / "runtime"
    worktree = tmp_path / "wt"
    worktree.mkdir(parents=True)

    monkeypatch.setattr(
        spawn_handler,
        "_call_spawn",
        lambda *a, **k: {"surface_ref": "surface:42", "rule_id": "x"},
    )
    monkeypatch.setattr(
        spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "prompt"
    )
    monkeypatch.setattr(spawn_handler, "_persona_materialised", lambda *a, **k: True)
    monkeypatch.setattr(spawn_handler.time, "sleep", lambda s: None)
    monkeypatch.setattr(spawn_handler, "_escalate", lambda ctx, reason: None)

    def _boom(*a, **k):
        raise RuntimeError("daemon attach exploded")

    monkeypatch.setattr(f"{_ATTACH_MOD}.attach_worker_daemon", _boom)

    ctx = CoachContext(
        issue_number=1084,
        runtime_dir=runtime_root,
        worktree_override=worktree,
        multiplexer_backend=object(),
        escalation_channel="file:./escalations.log",
        multiplexer_mode="pane",
    )
    result = spawn_handler.handle(ctx, Transition(src=Phase.GREEN, dst=Phase.SMOKE))
    assert result != HandlerResult.HANDLED

    decisions = runtime_root / "coach" / "decisions.jsonl"
    assert decisions.is_file(), "attach failure left no durable audit trail"
    blob = decisions.read_text()
    records = [json.loads(line) for line in blob.splitlines() if line.strip()]
    blocked = [
        r for r in records if r.get("outcome", {}).get("status") == "BLOCKED"
    ]
    assert blocked, f"no BLOCKED record to audit: {records}"

    # The trail must identify the specific unmediated worker (its surface ref).
    assert "surface:42" in blob, (
        "the BLOCKED audit record does not name the unmediated worker's surface "
        "— an operator cannot locate the worker to recover it (K002)"
    )
