# URN: test:spawn-agents:atdd-spawn-skeleton-and-harness:E002-UNIT-001-canonical-naming-and-layout-at-spawn
# Acceptance: acc:spawn-agents:E002-UNIT-001-canonical-name-applied
# Acceptance: acc:spawn-agents:E002-UNIT-002-rename-injected-into-agent
# Acceptance: acc:spawn-agents:E002-UNIT-003-layout-label-printed
# Acceptance: acc:spawn-agents:E002-UNIT-004-best-effort-on-rename-failure
# WMBT: wmbt:spawn-agents:E002
# Phase: RED
# Layer: application
"""E002-UNIT-001 — `atdd spawn` applies canonical naming and layout after
launching the multiplexer surface.

Issue #504 — K3 canonical-naming + layout pass at spawn.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pytest

from atdd.coach.utils.multiplexer import MultiplexerError
from atdd.coach.utils.session_naming import compute_issue_surface_name, target_grid_label

pytestmark = [pytest.mark.platform]


SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-v9-k3-canonical-naming-pass` |
| Train | `0002-coach-drives-lifecycle` |
| Feature | canonical naming sample |
"""


class FakeMultiplexer:
    name = "fake"

    def __init__(self, *, fail_rename: bool = False) -> None:
        self.fail_rename = fail_rename
        self.calls: list[dict] = []
        self._surface_counter = 0

    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> str:
        ref = f"workspace:{len(self.calls) + 1}"
        self.calls.append(
            {"op": "new_workspace", "cwd": cwd, "command": command, "name": name, "ref": ref}
        )
        return ref

    def new_surface(
        self,
        workspace_ref: Optional[str] = None,
        pane_ref: Optional[str] = None,
        cwd: Optional[str] = None,
        command: Optional[str] = None,
        name: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> str:
        self._surface_counter += 1
        ref = f"surface:{self._surface_counter}"
        self.calls.append(
            {
                "op": "new_surface",
                "workspace_ref": workspace_ref,
                "pane_ref": pane_ref,
                "cwd": cwd,
                "command": command,
                "name": name,
                "ref": ref,
            }
        )
        return ref

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})
        if self.fail_rename:
            raise MultiplexerError("rename failed")

    def new_persona_surface(
        self,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
        *,
        observer_runtime_root: str = "",
        observer_agent_id: str = "",
        observer_name: str = "",
        observer_command: str = "",
        **_: Any,
    ) -> str:
        persona_ref = self.new_surface(cwd=cwd, command=command, name=name)
        try:
            self.new_surface(cwd=cwd, command=observer_command, name=observer_name)
        except Exception:
            pass
        return persona_ref

    def send(self, ref: str, text: str) -> None:
        self.calls.append({"op": "send", "ref": ref, "text": text})

    def send_key(self, ref: str, key: str) -> None:
        self.calls.append({"op": "send_key", "ref": ref, "key": key})

    def read_screen(self, ref: str, lines: int = 50) -> str:
        return ""


def _spawn(tmp_path: Path, monkeypatch, fake_mx: FakeMultiplexer):
    from atdd.coach.commands import spawn
    from atdd.coach.commands import session_template

    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": SAMPLE_BODY},
    )
    monkeypatch.setattr(spawn, "compute_repo_short_name", lambda config: "ATDD", raising=False)
    monkeypatch.setattr(
        spawn, "load_atdd_config", lambda root: {"repo": {"short_name": "ATDD"}}, raising=False,
    )
    # M001 (#829): readiness gate and session-uuid capture are not under test here;
    # patch them out so the test does not block on filesystem / real Claude startup.
    monkeypatch.setattr(spawn, "_wait_for_claude_ready", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr(spawn, "capture_session_uuid", lambda *a, **kw: None, raising=False)
    monkeypatch.setenv("ATDD_CLAUDE_JSON_PATH", str(tmp_path / ".claude.json"))

    worktree = tmp_path / "feat-coach-v9-k3-canonical-naming-pass"
    worktree.mkdir(exist_ok=True)
    runtime = tmp_path / "rt"
    return spawn.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=worktree,
        issue=358,
        agent_id="coder-358-001",
        runtime_root=runtime,
        multiplexer=fake_mx,
    )


def test_spawn_applies_canonical_name_and_injects_rename(tmp_path, monkeypatch):
    """M001 (#829): backend.rename is called; no send/send_key for /rename injection."""
    fake_mx = FakeMultiplexer()
    result = _spawn(tmp_path, monkeypatch, fake_mx)
    # Issue #730: the spawn surface is named by issue identity only — ATDD<N>,
    # no slug/persona/phase — so it stays stable across phase transitions.
    canonical_name = compute_issue_surface_name("ATDD", 358)

    rename_calls = [c for c in fake_mx.calls if c["op"] == "rename"]
    assert rename_calls == [
        {"op": "rename", "ref": result["surface_ref"], "name": canonical_name}
    ]
    send_calls = [
        c for c in fake_mx.calls
        if c["op"] == "send" and "/rename" in c.get("text", "")
    ]
    assert send_calls == [], (
        f"M001 (#829): send('/rename ...') must NOT be called. Got: {send_calls}"
    )
    send_key_calls = [c for c in fake_mx.calls if c["op"] == "send_key"]
    assert send_key_calls == [], (
        f"M001 (#829): send_key must NOT be called for rename. Got: {send_key_calls}"
    )
    assert result["canonical_name"] == canonical_name
    assert result["canonical_rule_id"] == "coach.session.canonical-session-name"


def test_spawn_prints_layout_label(tmp_path, monkeypatch, capsys):
    fake_mx = FakeMultiplexer()
    _spawn(tmp_path, monkeypatch, fake_mx)

    captured = capsys.readouterr()
    assert target_grid_label(1) in captured.out
    assert "coach.session.layout-conformance" in captured.out


def test_spawn_rename_failure_is_best_effort(tmp_path, monkeypatch, capsys):
    """M001 (#829): rename failure is logged; spawn succeeds; no send() for /rename."""
    fake_mx = FakeMultiplexer(fail_rename=True)
    result = _spawn(tmp_path, monkeypatch, fake_mx)

    assert result["surface_ref"] == "surface:1"
    captured = capsys.readouterr()
    assert "coach.session.canonical-session-name" in captured.err
    assert "rename failed" in captured.err
