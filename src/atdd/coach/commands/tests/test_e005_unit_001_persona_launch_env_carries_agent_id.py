# URN: test:spawn-agents:persona-agent-id-env-injection:E005-UNIT-001-persona-launch-env-carries-agent-id
# Acceptance: acc:spawn-agents:E005-UNIT-001-persona-launch-env-carries-agent-id
# WMBT: wmbt:spawn-agents:E005
# Phase: RED
# Layer: application
"""E005-UNIT-001 — the persona launch invocation built by the coach spawn
path exports ``ATDD_AGENT_ID`` into the spawned process environment, equal
to the canonical ``agent_id``.

Issue #731 Phase 1 — ``_claude_code_adapter`` (spawn.py:68) launches
``claude`` with no env injection, so a coach-spawned persona inherits a
multiplexer environment with no ``ATDD_AGENT_ID`` and every ``atdd agent``
subcommand fails closed. The spawn path already knows the canonical
``agent_id``; it must export ``ATDD_AGENT_ID=<agent_id>`` into the persona
process.

RED: ``cmd_spawn`` dispatches the bare ``claude ...`` command with no env
prefix, so the assertions below fail until Phase 1 lands.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]

AGENT_ID = "tester-730-43be4d7f"

SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-spawned-persona-missing-atdd-agent-id` |
"""


class FakeMultiplexer:
    """Records the command dispatched for the persona surface."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._counter = 0

    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> str:
        ref = f"workspace:{len(self.calls) + 1}"
        self.calls.append({"op": "new_workspace", "cwd": cwd, "command": command, "name": name})
        return ref

    def new_surface(self, command: Optional[str] = None, name: Optional[str] = None, **kw: Any) -> str:
        self._counter += 1
        ref = f"surface:{self._counter}"
        self.calls.append({"op": "new_surface", "command": command, "name": name, "ref": ref})
        return ref

    def new_persona_surface(
        self,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
        *,
        observer_command: str = "",
        observer_name: str = "",
        **_: Any,
    ) -> str:
        persona_ref = self.new_surface(command=command, name=name)
        self.new_surface(command=observer_command, name=observer_name)
        return persona_ref

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})

    def send(self, ref: str, text: str) -> None:
        self.calls.append({"op": "send", "ref": ref, "text": text})

    def send_key(self, ref: str, key: str) -> None:
        self.calls.append({"op": "send_key", "ref": ref, "key": key})

    def paste_text(self, ref: str, text: str) -> None:
        self.calls.append({"op": "paste_text", "ref": ref, "text": text})

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


def _persona_command(fake_mx: FakeMultiplexer) -> str:
    """The command dispatched for the persona surface (surface:1)."""
    surfaces = [c for c in fake_mx.calls if c["op"] == "new_surface"]
    assert surfaces, "no surface was dispatched"
    return surfaces[0]["command"] or ""


def test_dispatched_persona_command_exports_atdd_agent_id(tmp_path, monkeypatch):
    fake_mx = FakeMultiplexer()
    _spawn(tmp_path, monkeypatch, fake_mx)
    command = _persona_command(fake_mx)
    assert "ATDD_AGENT_ID" in command, (
        f"persona launch command has no ATDD_AGENT_ID env injection: {command!r}"
    )


def test_injected_agent_id_equals_canonical_agent_id(tmp_path, monkeypatch):
    fake_mx = FakeMultiplexer()
    _spawn(tmp_path, monkeypatch, fake_mx)
    command = _persona_command(fake_mx)
    match = re.search(r"ATDD_AGENT_ID=(['\"]?)([^\s'\"]+)\1", command)
    assert match is not None, f"no ATDD_AGENT_ID=<value> token in command: {command!r}"
    assert match.group(2) == AGENT_ID


def test_returned_command_also_carries_agent_id(tmp_path, monkeypatch):
    fake_mx = FakeMultiplexer()
    result = _spawn(tmp_path, monkeypatch, fake_mx)
    assert f"ATDD_AGENT_ID={AGENT_ID}" in result["command"].replace('"', "").replace("'", "")


def test_injected_value_is_non_empty(tmp_path, monkeypatch):
    fake_mx = FakeMultiplexer()
    _spawn(tmp_path, monkeypatch, fake_mx)
    command = _persona_command(fake_mx)
    match = re.search(r"ATDD_AGENT_ID=(['\"]?)([^\s'\"]*)\1", command)
    assert match is not None and match.group(2) != "", "ATDD_AGENT_ID injected empty"
