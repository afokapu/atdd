# URN: test:coach-wave-orchestration:within-wave-concurrency-and-pane-identity:D001-UNIT-001-issue-surface-named-by-issue-identity
# Acceptance: acc:coach-wave-orchestration:D001-UNIT-001-issue-surface-named-by-issue-identity
# WMBT: wmbt:coach-wave-orchestration:D001
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""D001-UNIT-001 — the issue's persistent cmux surface is named ``ATDD<N>`` —
issue identity only, with no slug, persona, or phase segment.

RED: ``cmd_spawn`` names the surface ``compute_canonical_name(repo, issue,
slug)`` => ``ATDD<N>-<slug>``. This test pins the issue-identity-only name and
its stability across personas.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]

ISSUE = 730
EXPECTED_SURFACE_NAME = f"ATDD{ISSUE}"

SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-within-wave-serial-execution` |
| Train | `none` |
| Feature | persistent issue pane |
"""


class FakeCmuxMx:
    """cmux-style multiplexer double — records surface creations and names."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.created_names: list[str] = []

    def new_persona_surface(
        self, cwd: Any = None, command: Any = None, name: Any = None,
        *, observer_runtime_root: str = "", observer_agent_id: str = "",
        observer_name: str = "", observer_command: str = "", **_: Any,
    ) -> str:
        self.created_names.append(name)
        ref = f"pane:{len(self.calls) + 1}"
        self.calls.append({"op": "new_persona_surface", "name": name, "ref": ref})
        return ref

    def new_surface(self, workspace_ref: Any = None, pane_ref: Any = None,
                    cwd: Any = None, command: Any = None, name: Any = None,
                    direction: Any = None) -> str:
        self.created_names.append(name)
        ref = f"pane:{len(self.calls) + 1}"
        self.calls.append({"op": "new_surface", "name": name, "ref": ref})
        return ref

    def new_workspace(self, cwd: Any = None, command: Any = None,
                      name: Optional[str] = None) -> str:
        self.created_names.append(name)
        ref = f"pane:{len(self.calls) + 1}"
        self.calls.append({"op": "new_workspace", "name": name, "ref": ref})
        return ref

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

    def list_panes(self) -> list[dict]:
        return []

    def list_workspaces(self) -> list[str]:
        return []


def _spawn(tmp_path, monkeypatch, fake_mx, persona, phase):
    from atdd.coach.commands import spawn as cmd_spawn_mod
    from atdd.coach.commands import session_template

    monkeypatch.setattr(
        cmd_spawn_mod, "compute_repo_short_name", lambda config: "ATDD",
        raising=False,
    )
    monkeypatch.setattr(
        session_template, "fetch_issue",
        lambda n: {"number": n, "title": "persistent issue pane", "body": SAMPLE_BODY},
    )
    worktree = tmp_path / "feat-coach-within-wave-serial-execution"
    worktree.mkdir(exist_ok=True)
    return cmd_spawn_mod.cmd_spawn(
        persona=persona,
        llm="claude-code",
        worktree=worktree,
        issue=ISSUE,
        agent_id=f"{persona}-{ISSUE}-001",
        runtime_root=tmp_path / f"rt-{persona}",
        phase=phase,
        persona_prompt_content="",
        multiplexer=fake_mx,
        multiplexer_mode="pane",
    )


def test_issue_surface_named_by_issue_identity(tmp_path, monkeypatch):
    """The surface is named ATDD<N> for any persona — no slug/persona/phase."""
    planner_mx = FakeCmuxMx()
    planner = _spawn(tmp_path, monkeypatch, planner_mx, persona="planner", phase="planned")

    coder_mx = FakeCmuxMx()
    coder = _spawn(tmp_path, monkeypatch, coder_mx, persona="coder", phase="green")

    # The surface name is exactly ATDD<N> — issue identity only.
    assert planner["canonical_name"] == EXPECTED_SURFACE_NAME, (
        f"planner surface name {planner['canonical_name']!r} is not the bare "
        f"issue-identity name {EXPECTED_SURFACE_NAME!r}"
    )
    # It carries no slug, persona, or phase segment.
    assert planner_mx.created_names == [EXPECTED_SURFACE_NAME], planner_mx.created_names
    assert "planner" not in planner["canonical_name"]
    assert "planned" not in planner["canonical_name"]

    # The same surface name is produced regardless of which persona is spawning.
    assert coder["canonical_name"] == EXPECTED_SURFACE_NAME
    assert coder_mx.created_names == [EXPECTED_SURFACE_NAME]
    assert planner["canonical_name"] == coder["canonical_name"]
