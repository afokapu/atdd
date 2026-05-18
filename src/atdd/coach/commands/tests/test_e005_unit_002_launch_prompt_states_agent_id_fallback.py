# URN: test:spawn-agents:persona-agent-id-env-injection:E005-UNIT-002-launch-prompt-states-agent-id-fallback
# Acceptance: acc:spawn-agents:E005-UNIT-002-launch-prompt-states-agent-id-fallback
# WMBT: wmbt:spawn-agents:E005
# Phase: RED
# Layer: application
"""E005-UNIT-002 — the rendered launch prompt states the agent's own
``agent_id`` so a persona can fall back to ``--agent-id`` when the
``ATDD_AGENT_ID`` env var is ever missing.

Issue #731 Phase 1 (belt-and-braces) — ``_render_launch_prompt``
(spawn.py:135) currently never names the agent's own ``agent_id``.

RED: the rendered ``.launch_prompt.txt`` contains neither the canonical
``agent_id`` nor a ``--agent-id`` reference until Phase 1 lands.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]

AGENT_ID = "planner-731-4a1f4db3"

SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-spawned-persona-missing-atdd-agent-id` |
"""


class FakeMultiplexer:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._counter = 0

    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> str:
        self.calls.append({"op": "new_workspace"})
        return "workspace:1"

    def new_surface(self, command: Optional[str] = None, name: Optional[str] = None, **kw: Any) -> str:
        self._counter += 1
        ref = f"surface:{self._counter}"
        self.calls.append({"op": "new_surface", "command": command, "ref": ref})
        return ref

    def new_persona_surface(
        self, cwd: Any = None, command: Any = None, name: Any = None,
        *, observer_command: str = "", observer_name: str = "", **_: Any,
    ) -> str:
        persona_ref = self.new_surface(command=command, name=name)
        self.new_surface(command=observer_command, name=observer_name)
        return persona_ref

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename"})

    def send(self, ref: str, text: str) -> None:
        self.calls.append({"op": "send"})

    def send_key(self, ref: str, key: str) -> None:
        self.calls.append({"op": "send_key"})

    def paste_text(self, ref: str, text: str) -> None:
        self.calls.append({"op": "paste_text", "text": text})

    def read_screen(self, ref: str, lines: int = 50) -> str:
        return ""


def _spawn(tmp_path: Path, monkeypatch, fake_mx: FakeMultiplexer) -> dict:
    from atdd.coach.commands import session_template, spawn

    monkeypatch.setattr(
        session_template, "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": SAMPLE_BODY},
    )
    monkeypatch.setattr(spawn, "compute_repo_short_name", lambda config: "ATDD", raising=False)
    monkeypatch.setattr(
        spawn, "load_atdd_config", lambda root: {"repo": {"short_name": "ATDD"}}, raising=False,
    )
    worktree = tmp_path / "feat-coach-spawned-persona-missing-atdd-agent-id"
    worktree.mkdir(exist_ok=True)
    return spawn.cmd_spawn(
        persona="planner",
        llm="claude-code",
        worktree=worktree,
        issue=731,
        agent_id=AGENT_ID,
        runtime_root=tmp_path / "rt",
        multiplexer=fake_mx,
    )


def test_rendered_prompt_states_the_agent_id(tmp_path, monkeypatch):
    result = _spawn(tmp_path, monkeypatch, FakeMultiplexer())
    prompt = Path(result["launch_prompt_path"]).read_text()
    assert AGENT_ID in prompt, "launch prompt does not state the agent's own agent_id"


def test_rendered_prompt_references_agent_id_flag(tmp_path, monkeypatch):
    result = _spawn(tmp_path, monkeypatch, FakeMultiplexer())
    prompt = Path(result["launch_prompt_path"]).read_text()
    assert "--agent-id" in prompt, (
        "launch prompt does not mention the --agent-id fallback flag"
    )


def test_stated_agent_id_matches_canonical_agent_id(tmp_path, monkeypatch):
    """The agent_id stated in the prompt is the one passed to cmd_spawn."""
    fake_mx = FakeMultiplexer()
    result = _spawn(tmp_path, monkeypatch, fake_mx)
    prompt = Path(result["launch_prompt_path"]).read_text()
    pasted = [c for c in fake_mx.calls if c["op"] == "paste_text"]
    assert pasted, "launch prompt was never pasted into the surface"
    assert AGENT_ID in prompt and AGENT_ID in pasted[0]["text"]
