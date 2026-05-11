# URN: test:integration-hardening:coach-spawn-wiring:K1-INTEGRATION-002-persona-prompts-loaded
# Acceptance: acc:integration-hardening:K1-INTEGRATION-002-persona-prompts-loaded
# WMBT: wmbt:integration-hardening:K1
# Phase: RED
# Layer: integration
"""K1-INTEGRATION-002 — persona prompt is embedded in the launch prompt; missing
file aborts the transition and records BLOCKED in decisions.jsonl.

Verifies:
- Prompt content from the YAML file is passed to cmd_spawn as persona_prompt_content
- If the prompt YAML is absent, handle() returns HandlerResult.ERROR
- On missing prompt, a BLOCKED decision is appended to decisions.jsonl
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Phase, Transition

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Prompt content embedded in spawn call
# ---------------------------------------------------------------------------


def test_persona_prompt_content_passed_to_spawn(tmp_path, monkeypatch):
    """handle() must pass the loaded prompt text as persona_prompt_content."""
    from atdd.coach.handlers import spawn as spawn_handler

    expected_text = "You are a planner. Define WMBT and acceptance criteria."

    # Write a real prompt file in tmp_path so _load_persona_prompt picks it up.
    prompts_root = tmp_path / "prompts" / "persona"
    planner_dir = prompts_root / "planner"
    planner_dir.mkdir(parents=True)
    (planner_dir / "planned.prompt.yaml").write_text(
        yaml.dump({"persona": "planner", "phase": "PLANNED", "prompt": expected_text})
    )

    monkeypatch.setattr(spawn_handler, "_PROMPTS_ROOT", prompts_root)

    captured: dict = {}

    def fake_call_spawn(
        ctx: Any, persona: str, phase: str, llm: str,
        persona_prompt_content: str, worktree: Path,
        agent_id: str, runtime_root: Path,
    ) -> dict:
        captured["persona_prompt_content"] = persona_prompt_content
        return {"surface_ref": "fake:1", "rule_id": "test"}

    monkeypatch.setattr(spawn_handler, "_call_spawn", fake_call_spawn)
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: tmp_path / "wt")
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")
    (tmp_path / "wt").mkdir(parents=True)

    ctx = CoachContext(issue_number=585)
    result = spawn_handler.handle(
        ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED)
    )

    assert result == HandlerResult.HANDLED
    assert captured.get("persona_prompt_content") == expected_text, (
        f"expected persona prompt content to be passed, got {captured.get('persona_prompt_content')!r}"
    )


# ---------------------------------------------------------------------------
# Missing prompt file → ERROR + BLOCKED decision
# ---------------------------------------------------------------------------


def test_missing_prompt_file_returns_error(tmp_path, monkeypatch):
    """When the persona prompt YAML is missing, handle() must return HandlerResult.ERROR."""
    from atdd.coach.handlers import spawn as spawn_handler

    # Point to empty prompts_root (no files)
    monkeypatch.setattr(spawn_handler, "_PROMPTS_ROOT", tmp_path / "empty-prompts")
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")
    (tmp_path / ".atdd" / "runtime" / "coach").mkdir(parents=True)

    ctx = CoachContext(issue_number=585)
    result = spawn_handler.handle(
        ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED)
    )

    assert result == HandlerResult.ERROR, (
        f"expected ERROR on missing prompt file, got {result!r}"
    )


def test_missing_prompt_file_writes_blocked_decision(tmp_path, monkeypatch):
    """When the prompt file is missing, a BLOCKED decision is written to decisions.jsonl."""
    from atdd.coach.handlers import spawn as spawn_handler

    monkeypatch.setattr(spawn_handler, "_PROMPTS_ROOT", tmp_path / "empty-prompts")
    runtime_root = tmp_path / ".atdd" / "runtime"
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_root)

    ctx = CoachContext(issue_number=585)
    spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))

    decisions_path = runtime_root / "coach" / "decisions.jsonl"
    assert decisions_path.is_file(), "decisions.jsonl must exist after missing-prompt abort"

    records = [
        json.loads(line) for line in decisions_path.read_text().splitlines() if line.strip()
    ]
    assert len(records) >= 1, "at least one decision record must be written"
    record = records[-1]
    assert record["issue_number"] == 585
    assert record["decision_type"] == "abort"
    assert record["outcome"].get("status") == "BLOCKED"


def test_prompt_file_load_error_returns_error(tmp_path, monkeypatch):
    """If the prompt YAML is malformed, handle() returns ERROR."""
    from atdd.coach.handlers import spawn as spawn_handler

    prompts_root = tmp_path / "prompts" / "persona"
    bad_dir = prompts_root / "planner"
    bad_dir.mkdir(parents=True)
    (bad_dir / "planned.prompt.yaml").write_text("{{: invalid yaml :")

    monkeypatch.setattr(spawn_handler, "_PROMPTS_ROOT", prompts_root)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")

    ctx = CoachContext(issue_number=585)
    result = spawn_handler.handle(
        ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED)
    )
    assert result == HandlerResult.ERROR
