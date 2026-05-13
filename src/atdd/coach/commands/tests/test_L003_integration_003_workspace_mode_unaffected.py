# URN: test:integration-hardening:coach-single-command-driver:L003-INTEGRATION-003-workspace-mode-unaffected
# Acceptance: acc:integration-hardening:L003-INTEGRATION-003-workspace-mode-unaffected
# WMBT: wmbt:integration-hardening:L003
# Phase: RED
# Layer: integration
"""L003-INTEGRATION-003 — workspace mode: observer still uses new_surface, not new_surface_in_pane.

The tab-co-location change applies only to --multiplexer-mode pane. In workspace
mode, the observer must not call new_surface_in_pane (#658 out-of-scope clause).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.platform]


class _FakeMx:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._surface_pane: dict[str, str] = {}

    def new_workspace(self, cwd: str, command: str, name: Any = None) -> str:
        ref = f"workspace:{len(self.calls) + 1}"
        self.calls.append({"op": "new_workspace", "cwd": cwd, "command": command, "name": name, "ref": ref})
        return ref

    def new_surface(
        self,
        workspace_ref: Any = None,
        pane_ref: Any = None,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
        direction: Any = None,
    ) -> str:
        surface_ref = f"surface:{len(self.calls) + 1}"
        resolved_pane = pane_ref if pane_ref is not None else f"pane:{len(self.calls)}"
        self._surface_pane[surface_ref] = resolved_pane
        self.calls.append({"op": "new_surface", "pane_ref": resolved_pane, "cwd": cwd, "command": command, "name": name, "ref": surface_ref})
        return surface_ref

    def new_surface_in_pane(
        self,
        pane_ref: str,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
    ) -> str:
        surface_ref = f"surface:{len(self.calls) + 1}"
        self._surface_pane[surface_ref] = pane_ref
        self.calls.append({"op": "new_surface_in_pane", "pane_ref": pane_ref, "cwd": cwd, "command": command, "name": name, "ref": surface_ref})
        return surface_ref

    def surface_to_pane(self, surface_ref: str) -> str:
        return self._surface_pane[surface_ref]

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})

    def read_screen(self, ref: str, lines: int = 50) -> str:
        return ""

    def send(self, ref: str, text: str) -> None:
        pass

    def send_key(self, ref: str, key: str) -> None:
        pass

    def list_workspaces(self) -> list[str]:
        return []

    def close(self, ref: str) -> None:
        pass


def test_workspace_mode_observer_does_not_use_new_surface_in_pane(tmp_path, monkeypatch):
    """workspace mode: observer must not call new_surface_in_pane."""
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.handlers.state_machine import CoachContext, Phase, Transition, HandlerResult
    from atdd.coach.commands import spawn as cmd_spawn_mod

    fake_mx = _FakeMx()
    wt = tmp_path / "wt"
    wt.mkdir()

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx)

    ctx = CoachContext(
        issue_number=658,
        llm="claude-code",
        multiplexer=fake_mx,
        multiplexer_mode="workspace",
        dry_run=False,
        max_retries=0,
        escalation_channel=None,
        persona_llm={},
        coach_run_id=None,
        runtime_dir=str(tmp_path / ".atdd" / "runtime"),
    )
    transition = Transition(src=Phase.INIT, dst=Phase.PLANNED)
    result = spawn_handler.handle(ctx, transition)
    assert result == HandlerResult.HANDLED

    tab_calls = [c for c in fake_mx.calls if c["op"] == "new_surface_in_pane"]
    assert len(tab_calls) == 0, (
        f"workspace mode must not call new_surface_in_pane; got: {tab_calls}"
    )

    observer_spawns = [
        c for c in fake_mx.calls
        if c["op"] in ("new_surface", "new_workspace")
        and "observer" in (c.get("name") or "").lower()
    ]
    assert len(observer_spawns) >= 1, (
        f"Expected at least 1 observer spawn in workspace mode; calls={fake_mx.calls}"
    )
