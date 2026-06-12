# URN: test:mediate-worker-decisions:feed-daemon-durability:K002-UNIT-001-attach-failure-writes-durable-blocked-not-handled
# Acceptance: acc:mediate-worker-decisions:K002-UNIT-001-attach-failure-writes-durable-blocked-not-handled
# WMBT: wmbt:mediate-worker-decisions:K002
# Phase: RED
# Layer: application
# Assertion: behavioral
"""K002-UNIT-001 — a dispatch→daemon attach failure BLOCKS, never returns HANDLED.

When the post-spawn decision-daemon attach fails, the worker is spawned but
unmediated — it will park forever on its first decision. Today
``_attach_worker_daemon`` swallows the failure to stderr and ``handle`` proceeds
to ``HANDLED``: the only blocker path that writes neither a decision nor an
escalation. On attach failure ``handle`` MUST escalate, write a durable BLOCKED
decision, and return a non-HANDLED result.

RED: today an attach failure is logged-and-ignored and ``handle`` returns
``HANDLED`` with no durable trail. Fails until the BLOCK-on-attach-failure
behaviour lands.
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


def _drive_handle_with_failing_attach(tmp_path, monkeypatch, escalations):
    from atdd.coach.handlers import spawn as spawn_handler

    runtime_root = tmp_path / ".atdd" / "runtime"
    worktree = tmp_path / "wt"
    worktree.mkdir(parents=True)

    # Spawn succeeds and the persona materialises, so handle() reaches the
    # post-spawn daemon-attach step.
    monkeypatch.setattr(
        spawn_handler,
        "_call_spawn",
        lambda *a, **k: {"surface_ref": "surface:7", "rule_id": "x"},
    )
    monkeypatch.setattr(
        spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "prompt"
    )
    monkeypatch.setattr(spawn_handler, "_persona_materialised", lambda *a, **k: True)
    monkeypatch.setattr(spawn_handler.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        spawn_handler, "_escalate", lambda ctx, reason: escalations.append(reason)
    )

    # Induce the attach failure at the real seam: the inner attach raises.
    def _boom(*a, **k):
        raise RuntimeError("daemon workspace unreachable")

    monkeypatch.setattr(f"{_ATTACH_MOD}.attach_worker_daemon", _boom)

    ctx = CoachContext(
        issue_number=1084,
        runtime_dir=runtime_root,
        worktree_override=worktree,
        multiplexer_backend=object(),  # non-None → skips _resolve_multiplexer
        escalation_channel="file:./escalations.log",
        multiplexer_mode="pane",
    )
    result = spawn_handler.handle(ctx, Transition(src=Phase.GREEN, dst=Phase.SMOKE))
    return result, runtime_root


def test_attach_failure_blocks_and_writes_durable_decision(tmp_path, monkeypatch):
    escalations: list[str] = []
    result, runtime_root = _drive_handle_with_failing_attach(
        tmp_path, monkeypatch, escalations
    )

    assert result != HandlerResult.HANDLED, (
        "attach failure left handle() returning HANDLED for an UNMEDIATED "
        "worker — it must BLOCK instead (K002/A1)"
    )

    assert len(escalations) == 1, (
        f"attach failure must escalate exactly once, got {escalations}"
    )

    decisions = runtime_root / "coach" / "decisions.jsonl"
    assert decisions.is_file(), (
        "attach failure wrote no durable decision — the only blocker path with "
        "no trail (K002/A1)"
    )
    records = [
        json.loads(line)
        for line in decisions.read_text().splitlines()
        if line.strip()
    ]
    assert any(
        r.get("outcome", {}).get("status") == "BLOCKED" for r in records
    ), f"no BLOCKED decision recorded for the attach failure: {records}"
