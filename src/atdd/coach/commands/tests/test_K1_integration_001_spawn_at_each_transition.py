# URN: test:integration-hardening:coach-spawn-wiring:K1-INTEGRATION-001-spawn-at-each-transition
# Acceptance: acc:integration-hardening:K1-INTEGRATION-001-spawn-at-each-transition
# WMBT: wmbt:integration-hardening:K1
# Phase: RED
# Layer: integration
"""K1-INTEGRATION-001 — atdd coach spawns the right persona at each of the 5 phase
transitions defined in spec §4.1.

For each transition in the persona-per-transition table, handle() must:
- Return HandlerResult.HANDLED (not NOOP or ERROR)
- Invoke spawn with the correct persona matching the table
- Return HandlerResult.NOOP for transitions not in the table
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Phase, Transition

pytestmark = [pytest.mark.platform]

# (src_phase, dst_phase, expected_persona, expected_agent_phase)
PERSONA_TABLE = [
    (Phase.INIT, Phase.PLANNED, "planner", "planned"),
    (Phase.PLANNED, Phase.RED, "tester", "red"),
    (Phase.RED, Phase.GREEN, "coder", "green"),
    (Phase.GREEN, Phase.SMOKE, "tester", "smoke"),
    (Phase.SMOKE, Phase.REFACTOR, "coder", "refactor"),
]

SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-v9-k1-spawn-wiring-585` |
| Train | `0004-integration-hardening` |
| Feature | coach spawn wiring |
"""


class FakeMultiplexer:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def new_workspace(self, cwd: str, command: str, name: Any = None) -> str:
        ref = f"workspace:{len(self.calls) + 1}"
        self.calls.append({"op": "new_workspace", "cwd": cwd, "command": command, "ref": ref})
        return ref

    def new_surface(self, workspace_ref: Any = None, pane_ref: Any = None,
                    cwd: Any = None, command: Any = None,
                    name: Any = None, direction: Any = None) -> str:
        ref = f"surface:{len(self.calls) + 1}"
        self.calls.append({"op": "new_surface", "cwd": cwd, "command": command, "ref": ref})
        return ref

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})


# ---------------------------------------------------------------------------
# Persona mapping correctness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("src,dst,expected_persona,expected_phase", PERSONA_TABLE)
def test_handle_returns_handled_for_each_transition(
    src, dst, expected_persona, expected_phase, tmp_path, monkeypatch
):
    """handle() must return HANDLED (not NOOP) for all 5 persona transitions."""
    from atdd.coach.handlers import spawn as spawn_handler

    captured: dict = {}

    def fake_call_spawn(
        ctx: Any, persona: str, phase: str, llm: str,
        persona_prompt_content: str, worktree: Path,
        agent_id: str, runtime_root: Path,
    ) -> dict:
        captured["persona"] = persona
        captured["phase"] = phase
        captured["llm"] = llm
        return {"surface_ref": "fake:1", "rule_id": "test"}

    monkeypatch.setattr(spawn_handler, "_call_spawn", fake_call_spawn)
    monkeypatch.setattr(
        spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt"
    )
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: tmp_path / "wt")
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")
    (tmp_path / "wt").mkdir(parents=True)

    ctx = CoachContext(issue_number=585)
    result = spawn_handler.handle(ctx, Transition(src=src, dst=dst))

    assert result == HandlerResult.HANDLED, (
        f"expected HANDLED for {src}→{dst}, got {result!r}"
    )
    assert captured.get("persona") == expected_persona, (
        f"expected persona {expected_persona!r} for {src}→{dst}, "
        f"got {captured.get('persona')!r}"
    )
    assert captured.get("phase") == expected_phase, (
        f"expected phase {expected_phase!r} for {src}→{dst}, "
        f"got {captured.get('phase')!r}"
    )


def test_handle_returns_noop_for_unrecognized_transition(tmp_path, monkeypatch):
    """REFACTOR→COMPLETE is a reviewer-driven transition (owned by #589), not a spawn."""
    from atdd.coach.handlers import spawn as spawn_handler

    ctx = CoachContext(issue_number=585)
    result = spawn_handler.handle(
        ctx, Transition(src=Phase.REFACTOR, dst=Phase.COMPLETE)
    )
    assert result == HandlerResult.NOOP


# ---------------------------------------------------------------------------
# Spawn manifest written at .atdd/runtime/agents/<id>/
# ---------------------------------------------------------------------------


def test_spawn_manifest_written_after_handle(tmp_path, monkeypatch):
    """After handle(), a manifest.json must exist under .atdd/runtime/agents/<id>/."""
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import session_template, spawn as cmd_spawn_mod

    monkeypatch.setattr(
        session_template, "fetch_issue",
        lambda n: {"number": n, "title": "spawn wiring", "body": SAMPLE_BODY},
    )
    fake_mx = FakeMultiplexer()
    monkeypatch.setattr(
        cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx
    )

    wt = tmp_path / "feat-coach-v9-k1-spawn-wiring-585"
    wt.mkdir(parents=True)
    runtime_root = tmp_path / ".atdd" / "runtime"

    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(
        spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt"
    )

    ctx = CoachContext(issue_number=585)
    result = spawn_handler.handle(
        ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED)
    )

    assert result == HandlerResult.HANDLED
    agents_dir = runtime_root / "agents"
    assert agents_dir.is_dir(), "agents/ dir must exist under runtime root"
    manifests = list(agents_dir.glob("*/manifest.json"))
    assert len(manifests) == 1, f"expected one manifest.json, found {manifests}"
