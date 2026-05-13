# URN: test:integration-hardening:coach-single-command-driver:L003-INTEGRATION-002-pane-count-unchanged
# Acceptance: acc:integration-hardening:L003-INTEGRATION-002-pane-count-unchanged
# WMBT: wmbt:integration-hardening:L003
# Phase: RED
# Layer: integration
"""L003-INTEGRATION-002 — 6 agents in pane mode → 6 panes, not 12.

Each of 6 handle(INIT→PLANNED) calls produces 1 new_surface (persona) and
1 new_surface_in_pane (observer) sharing the same pane_ref. No extra panes.
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


def test_six_agents_produce_six_panes_not_twelve(tmp_path, monkeypatch):
    """6 handle() calls in pane mode → 6 new_surface + 6 new_surface_in_pane; same 6 pane_refs."""
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

    transition = Transition(src=Phase.INIT, dst=Phase.PLANNED)

    for issue_n in range(100, 106):
        ctx = CoachContext(
            issue_number=issue_n,
            llm="claude-code",
            multiplexer=fake_mx,
            multiplexer_mode="pane",
            dry_run=False,
            max_retries=0,
            escalation_channel=None,
            persona_llm={},
            coach_run_id=None,
            runtime_dir=str(tmp_path / ".atdd" / "runtime"),
        )
        result = spawn_handler.handle(ctx, transition)
        assert result == HandlerResult.HANDLED, f"Expected HANDLED for issue {issue_n}"

    persona_calls = [c for c in fake_mx.calls if c["op"] == "new_surface"]
    observer_calls = [c for c in fake_mx.calls if c["op"] == "new_surface_in_pane"]

    assert len(persona_calls) == 6, (
        f"Expected exactly 6 persona new_surface calls, got {len(persona_calls)}"
    )
    assert len(observer_calls) == 6, (
        f"Expected exactly 6 observer new_surface_in_pane calls, got {len(observer_calls)}"
    )

    # Each observer must share the pane_ref of its corresponding persona
    for i, (persona_c, observer_c) in enumerate(zip(persona_calls, observer_calls)):
        assert persona_c["pane_ref"] == observer_c["pane_ref"], (
            f"Agent {i}: persona pane {persona_c['pane_ref']!r} != observer pane {observer_c['pane_ref']!r}"
        )
