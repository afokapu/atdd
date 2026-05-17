# URN: test:spawn-agents:persona-agent-id-env-injection:E005-INTEGRATION-001-atdd-agent-done-resolves-from-injected-env
# Acceptance: acc:spawn-agents:E005-INTEGRATION-001-atdd-agent-done-resolves-from-injected-env
# WMBT: wmbt:spawn-agents:E005
# Phase: RED
# Layer: integration
"""E005-INTEGRATION-001 — a persona whose environment carries the
spawn-injected ``ATDD_AGENT_ID`` can run ``atdd agent done`` with no
``--agent-id`` argument, and the ``done.json`` the coach polls for is
written.

Issue #731 Phase 1 — ties the spawn-path env injection to the
``atdd agent`` handshake CLI. ``agent.cmd_done`` already resolves the id
from ``ATDD_AGENT_ID`` (agent.py:101); the missing half is the spawn path
putting it there.

RED: ``cmd_spawn`` emits a launch command with no ``ATDD_AGENT_ID=`` token,
so the environment a persona would inherit has no agent id and the
no-``--agent-id`` handshake cannot resolve.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]

AGENT_ID = "tester-731-9c2e1a04"

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
        pass

    def send(self, ref: str, text: str) -> None:
        pass

    def send_key(self, ref: str, key: str) -> None:
        pass

    def paste_text(self, ref: str, text: str) -> None:
        pass

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
        persona="tester",
        llm="claude-code",
        worktree=worktree,
        issue=731,
        agent_id=AGENT_ID,
        runtime_root=tmp_path / "rt",
        multiplexer=fake_mx,
    )


def _env_from_command(command: str) -> dict[str, str]:
    """Extract KEY=VALUE env tokens injected into the launch command."""
    return {
        m.group(1): m.group(3)
        for m in re.finditer(r"\b([A-Z][A-Z0-9_]*)=(['\"]?)([^\s'\"]*)\2", command)
    }


def test_persona_environment_carries_agent_id(tmp_path, monkeypatch):
    result = _spawn(tmp_path, monkeypatch, FakeMultiplexer())
    env = _env_from_command(result["command"])
    assert env.get("ATDD_AGENT_ID") == AGENT_ID, (
        f"spawn-injected environment has no usable ATDD_AGENT_ID: {env!r}"
    )


def test_done_resolves_from_injected_env_without_agent_id_flag(tmp_path, monkeypatch):
    """With only the spawn-injected ATDD_AGENT_ID in the environment and no
    --agent-id, ``agent.cmd_done`` resolves the agent and writes done.json."""
    from atdd.coach.commands import agent

    result = _spawn(tmp_path, monkeypatch, FakeMultiplexer())
    env = _env_from_command(result["command"])
    injected = env.get("ATDD_AGENT_ID")
    assert injected, "no ATDD_AGENT_ID injected by the spawn path"

    monkeypatch.setenv("ATDD_AGENT_ID", injected)
    runtime = tmp_path / "rt"
    # No explicit agent_id — resolution must come from the env var alone.
    agent.cmd_done(summary="PLANNED: deliverables written", runtime_root=runtime)

    # done.json lands under agents/<agent_id>/ — the path proves the handshake
    # resolved the canonical agent_id from the env var, with no --agent-id.
    done = runtime / "agents" / AGENT_ID / "done.json"
    assert done.exists(), "done.json was not written — coach RuntimeWatcher would stall"
    record = json.loads(done.read_text())
    assert record.get("summary") == "PLANNED: deliverables written"
