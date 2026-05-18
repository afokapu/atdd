# URN: test:spawn-agents:smoke-persona-spawn-integrity:E006-UNIT-003-incomplete-persona-spawn-maps-to-error
# Acceptance: acc:spawn-agents:E006-UNIT-003-incomplete-persona-spawn-maps-to-error
# WMBT: wmbt:spawn-agents:E006
# Phase: RED
# Layer: unit
"""E006-UNIT-003 — an incomplete persona spawn makes ``handle()`` return
``HandlerResult.ERROR``, escalate, and write a BLOCKED decision — never
``HANDLED``.

When the spawn path completes (``cmd_spawn`` returns) but the persona never
materialised — no agent runtime dir, no manifest, no ``agent_spawned`` event —
the GREEN→SMOKE ``handle()`` MUST treat it as a failure: return
``HandlerResult.ERROR``, invoke ``_escalate`` exactly once, and append a
BLOCKED decision to the runtime decisions log.

RED: today ``_spawn_with_retries`` treats only a *raised exception* as
failure, so a truthy ``cmd_spawn`` return — even with nothing on disk — flows
through to ``HANDLED``. This test fails until the materialisation check (#733)
lands.
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


def test_incomplete_persona_spawn_returns_error_escalates_and_blocks(
    tmp_path, monkeypatch
):
    """A cmd_spawn that returns without materialising the persona yields ERROR
    + one escalation + a BLOCKED decision."""
    from atdd.coach.handlers import spawn as spawn_handler

    runtime_root = tmp_path / ".atdd" / "runtime"
    worktree = tmp_path / "wt"
    worktree.mkdir(parents=True)

    # cmd_spawn-level stub: returns a truthy result dict but materialises
    # NOTHING — no agent runtime dir, no manifest, no agent_spawned event.
    def _stub_call_spawn(ctx, persona, phase, llm, prompt, wt, agent_id, rt):  # noqa: ANN001
        return {"surface_ref": "surface:1", "rule_id": "coach.spawn.atdd-spawn-cli"}

    monkeypatch.setattr(spawn_handler, "_call_spawn", _stub_call_spawn)
    monkeypatch.setattr(
        spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt"
    )
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: worktree)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(spawn_handler.time, "sleep", lambda s: None)

    escalations: list[str] = []
    monkeypatch.setattr(
        spawn_handler, "_escalate", lambda ctx, reason: escalations.append(reason)
    )

    ctx = CoachContext(
        issue_number=733,
        escalation_channel="file:./escalations.log",
        multiplexer_mode="pane",
    )
    result = spawn_handler.handle(
        ctx, Transition(src=Phase.GREEN, dst=Phase.SMOKE)
    )

    assert result == HandlerResult.ERROR, (
        f"an incomplete persona spawn must yield HandlerResult.ERROR, not "
        f"{result} — a HANDLED return leaves the coach blocked on a SMOKE "
        f"done.json no persona exists to write (#733)"
    )
    assert len(escalations) == 1, (
        f"_escalate must be invoked exactly once on persona-spawn failure, "
        f"got {escalations}"
    )

    decisions = runtime_root / "coach" / "decisions.jsonl"
    assert decisions.is_file(), (
        "a BLOCKED decision record must be written to the runtime decisions log"
    )
    records = [
        json.loads(line)
        for line in decisions.read_text().splitlines()
        if line.strip()
    ]
    assert any(
        r.get("outcome", {}).get("status") == "BLOCKED" for r in records
    ), f"no BLOCKED decision found in decisions.jsonl: {records}"
