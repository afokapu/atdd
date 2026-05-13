# URN: test:integration-hardening:coach-single-command-driver:L003-INTEGRATION-001-observer-is-tab-not-pane
# Acceptance: acc:integration-hardening:L003-INTEGRATION-001-observer-is-tab-not-pane
# WMBT: wmbt:integration-hardening:L003
# Phase: RED
# Layer: integration
"""L003-INTEGRATION-001 — pane mode: observer placed as tab in persona's pane, not a new pane.

In pane mode, handle(ctx, INIT→PLANNED) must call new_surface (persona) and then
new_surface_in_pane (observer) sharing the same pane_ref — never a second new_surface
for the observer (#658).
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


def _make_ctx(tmp_path: Path, fake_mx: _FakeMx):
    from atdd.coach.handlers.state_machine import CoachContext

    return CoachContext(
        issue_number=658,
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


def test_observer_placed_as_tab_in_persona_pane(tmp_path, monkeypatch):
    """In pane mode, observer uses new_surface_in_pane sharing persona's pane_ref."""
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.handlers.state_machine import Phase, Transition, HandlerResult
    from atdd.coach.commands import spawn as cmd_spawn_mod

    fake_mx = _FakeMx()
    wt = tmp_path / "wt"
    wt.mkdir()

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx)

    ctx = _make_ctx(tmp_path, fake_mx)
    transition = Transition(src=Phase.INIT, dst=Phase.PLANNED)

    result = spawn_handler.handle(ctx, transition)
    assert result == HandlerResult.HANDLED, f"Expected HANDLED, got {result}"

    persona_calls = [c for c in fake_mx.calls if c["op"] == "new_surface"]
    observer_calls = [c for c in fake_mx.calls if c["op"] == "new_surface_in_pane"]

    assert len(persona_calls) >= 1, f"Expected >=1 new_surface (persona), got: {fake_mx.calls}"
    assert len(observer_calls) == 1, f"Expected 1 new_surface_in_pane (observer), got: {fake_mx.calls}"

    # Observer must share the persona's pane
    persona_pane = persona_calls[-1]["pane_ref"]
    observer_pane = observer_calls[0]["pane_ref"]
    assert persona_pane == observer_pane, (
        f"Observer pane_ref {observer_pane!r} must match persona pane_ref {persona_pane!r}"
    )


def test_observer_name_contains_observer_and_phase(tmp_path, monkeypatch):
    """Observer surface name follows ATDD<N>-observer-<phase> pattern in pane mode."""
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.handlers.state_machine import Phase, Transition
    from atdd.coach.commands import spawn as cmd_spawn_mod

    fake_mx = _FakeMx()
    wt = tmp_path / "wt"
    wt.mkdir()

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx)

    ctx = _make_ctx(tmp_path, fake_mx)
    transition = Transition(src=Phase.INIT, dst=Phase.PLANNED)
    spawn_handler.handle(ctx, transition)

    observer_calls = [c for c in fake_mx.calls if c["op"] == "new_surface_in_pane"]
    assert observer_calls, "Expected new_surface_in_pane call for observer"

    name = observer_calls[0].get("name") or ""
    assert "observer" in name.lower(), f"Observer name should contain 'observer', got: {name!r}"
    assert "planned" in name.lower() or "658" in name, (
        f"Observer name should reference phase or issue, got: {name!r}"
    )
