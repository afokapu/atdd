# URN: test:integration-hardening:coach-spawn-wiring:K001-INTEGRATION-003-persona-llm-honored
# Acceptance: acc:integration-hardening:K001-INTEGRATION-003-persona-llm-honored
# WMBT: wmbt:integration-hardening:K001
# Phase: RED
# Layer: integration
"""K001-INTEGRATION-003 — --persona-llm flag routes each persona to the configured LLM.

Verifies that when CoachContext.persona_llm is set (from --persona-llm CLI flag),
each spawn call uses the mapped LLM for the given persona. Fallback to ctx.llm
and then to "claude-code" default is also tested.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Phase, Transition

pytestmark = [pytest.mark.platform]


def _make_fake_spawn(captured: dict):
    def fake_call_spawn(
        ctx: Any, persona: str, phase: str, llm: str,
        persona_prompt_content: str, worktree: Path,
        agent_id: str, runtime_root: Path,
    ) -> dict:
        captured.setdefault("calls", []).append({"persona": persona, "llm": llm})
        return {"surface_ref": "fake:1", "rule_id": "test"}
    return fake_call_spawn


def _patch_handler(monkeypatch, tmp_path, spawn_handler, fake_spawn):
    monkeypatch.setattr(spawn_handler, "_call_spawn", fake_spawn)
    monkeypatch.setattr(
        spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt"
    )
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: tmp_path / "wt")
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")
    (tmp_path / "wt").mkdir(parents=True, exist_ok=True)


def test_persona_llm_planner_honored(tmp_path, monkeypatch):
    """planner spawn must use the LLM mapped in --persona-llm."""
    from atdd.coach.handlers import spawn as spawn_handler

    captured: dict = {}
    _patch_handler(monkeypatch, tmp_path, spawn_handler, _make_fake_spawn(captured))

    ctx = CoachContext(issue_number=585, persona_llm={"planner": "glm-5.1"})
    spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))

    calls = captured.get("calls", [])
    assert len(calls) == 1
    assert calls[0]["persona"] == "planner"
    assert calls[0]["llm"] == "glm-5.1", (
        f"expected LLM 'glm-5.1', got {calls[0]['llm']!r}"
    )


def test_persona_llm_tester_and_coder_honored(tmp_path, monkeypatch):
    """Each persona in persona_llm must use its mapped LLM."""
    from atdd.coach.handlers import spawn as spawn_handler

    persona_llm = {
        "tester": "glm-5.1",
        "coder": "claude-sonnet-4-6",
    }
    transitions = [
        (Phase.PLANNED, Phase.RED, "tester", "glm-5.1"),
        (Phase.RED, Phase.GREEN, "coder", "claude-sonnet-4-6"),
        (Phase.GREEN, Phase.SMOKE, "tester", "glm-5.1"),
        (Phase.SMOKE, Phase.REFACTOR, "coder", "claude-sonnet-4-6"),
    ]

    for src, dst, expected_persona, expected_llm in transitions:
        captured: dict = {}
        _patch_handler(monkeypatch, tmp_path, spawn_handler, _make_fake_spawn(captured))
        ctx = CoachContext(issue_number=585, persona_llm=persona_llm)
        spawn_handler.handle(ctx, Transition(src=src, dst=dst))
        calls = captured.get("calls", [])
        assert calls and calls[0]["llm"] == expected_llm, (
            f"{src}→{dst}: expected LLM {expected_llm!r}, got {calls[0].get('llm')!r}"
        )


def test_fallback_to_ctx_llm(tmp_path, monkeypatch):
    """When persona_llm has no entry for this persona, fall back to ctx.llm."""
    from atdd.coach.handlers import spawn as spawn_handler

    captured: dict = {}
    _patch_handler(monkeypatch, tmp_path, spawn_handler, _make_fake_spawn(captured))

    ctx = CoachContext(issue_number=585, llm="claude-opus-4-7", persona_llm={})
    spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))

    calls = captured.get("calls", [])
    assert calls and calls[0]["llm"] == "claude-opus-4-7", (
        f"expected ctx.llm fallback 'claude-opus-4-7', got {calls[0].get('llm')!r}"
    )


def test_fallback_to_default_llm(tmp_path, monkeypatch):
    """When persona_llm and ctx.llm are both unset, use 'claude-code' default."""
    from atdd.coach.handlers import spawn as spawn_handler

    captured: dict = {}
    _patch_handler(monkeypatch, tmp_path, spawn_handler, _make_fake_spawn(captured))

    ctx = CoachContext(issue_number=585, llm=None, persona_llm={})
    spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))

    calls = captured.get("calls", [])
    assert calls and calls[0]["llm"] == "claude-code", (
        f"expected default LLM 'claude-code', got {calls[0].get('llm')!r}"
    )
