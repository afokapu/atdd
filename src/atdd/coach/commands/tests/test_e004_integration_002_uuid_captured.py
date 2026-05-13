# URN: test:integration-hardening:coach-spawn-wiring:E004-INTEGRATION-002-uuid-captured
# Acceptance: acc:integration-hardening:E004-INTEGRATION-002-uuid-captured
# WMBT: wmbt:integration-hardening:E004
# Phase: RED
# Layer: integration
"""E004-INTEGRATION-002 — cmd_spawn writes .session.json with claude_resume_uuid.

FakeMultiplexer with a pre-seeded screen containing 'claude --resume <UUID>'
simulates a Claude Code surface that has just started.  Calling cmd_spawn through
the full pipeline must produce a .session.json file under runtime_root with a
valid UUID.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]

VALID_UUID = "0ccd5309-7dbf-4590-bf92-7d128903bd42"
RESUME_SCREEN = (
    "Claude Code · Sonnet 4.6\n"
    f"Resume this session with: claude --resume {VALID_UUID}\n"
    "> "
)

SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `fix/652-claude-session-rename` |
| Train | `0002-coach-drives-lifecycle` |
| Feature | session rename uuid |
"""


class _FakeMx:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._counter = 0

    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> str:
        ref = f"workspace:{self._counter + 1}"
        self._counter += 1
        self.calls.append({"op": "new_workspace", "ref": ref})
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
        self._counter += 1
        ref = f"surface:{self._counter}"
        self.calls.append({"op": "new_surface", "ref": ref})
        return ref

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})

    def send(self, ref: str, text: str) -> None:
        self.calls.append({"op": "send", "ref": ref, "text": text})

    def send_key(self, ref: str, key: str) -> None:
        self.calls.append({"op": "send_key", "ref": ref, "key": key})

    def read_screen(self, ref: str, lines: int = 50) -> str:
        return RESUME_SCREEN

    def list_workspaces(self) -> list[str]:
        return []

    def close(self, ref: str) -> None:
        pass


def test_cmd_spawn_writes_session_json_with_uuid(tmp_path: Path, monkeypatch) -> None:
    """cmd_spawn writes .session.json containing claude_resume_uuid after spawn."""
    from atdd.coach.commands import spawn
    from atdd.coach.commands import session_template
    import atdd.coach.utils.session_naming_apply as sna

    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "fix session rename", "body": SAMPLE_BODY},
    )
    monkeypatch.setattr(spawn, "compute_repo_short_name", lambda config: "ATDD", raising=False)
    monkeypatch.setattr(
        spawn, "load_atdd_config", lambda root: {"repo": {"short_name": "ATDD"}}, raising=False
    )
    # Eliminate the sleep inside capture_session_uuid
    monkeypatch.setattr(sna, "time", type("_T", (), {"sleep": staticmethod(lambda d: None)})())

    fake_mx = _FakeMx()
    worktree = tmp_path / "fix-652-claude-session-rename"
    worktree.mkdir()
    runtime = tmp_path / "rt"

    result = spawn.cmd_spawn(
        persona="planner",
        llm="claude-code",
        worktree=worktree,
        issue=652,
        agent_id="planner-652-001",
        runtime_root=runtime,
        multiplexer=fake_mx,
    )

    session_file = runtime / "coach" / "652" / "planner-652-001.session.json"
    assert session_file.exists(), (
        f".session.json not found at {session_file}; "
        f"runtime tree: {list(runtime.rglob('*'))}"
    )

    data = json.loads(session_file.read_text())
    import re
    uuid_pattern = re.compile(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}")
    assert uuid_pattern.fullmatch(data["claude_resume_uuid"]), (
        f"claude_resume_uuid does not match UUID pattern: {data['claude_resume_uuid']!r}"
    )
    assert data["claude_resume_uuid"] == VALID_UUID
    assert data["issue"] == 652
    assert data["agent_id"] == "planner-652-001"
