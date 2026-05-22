# URN: test:consolidate-coach-workspace:headless-observer:Y002-UNIT-001-persona-spawn-creates-no-obs-surface
# Acceptance: acc:consolidate-coach-workspace:Y002-UNIT-001-persona-spawn-creates-no-obs-surface
# WMBT: wmbt:consolidate-coach-workspace:Y002
# Phase: GREEN
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""Y002-UNIT-001 — spawning a persona via handlers/spawn.handle creates no
observer surface (issue #754).

Issue #754 removed per-worker observer spawning entirely. The coach-level
MultiAgentObserver is started once by _execute_cold_start. handlers/spawn.handle
must create zero observer surfaces — neither ':obs' panes nor any surface
whose name contains 'observer'.
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
        self.calls.append({"op": "new_workspace", "name": name, "ref": ref})
        return ref

    def new_surface(self, workspace_ref: Any = None, pane_ref: Any = None,
                    cwd: Any = None, command: Any = None, name: Any = None,
                    direction: Any = None) -> str:
        ref = f"surface:{len(self.calls) + 1}"
        self._surface_pane[ref] = pane_ref or f"pane:{len(self.calls)}"
        self.calls.append({"op": "new_surface", "name": name, "ref": ref})
        return ref

    def new_surface_in_pane(self, pane_ref: str, cwd: Any = None,
                             command: Any = None, name: Any = None) -> str:
        ref = f"surface:{len(self.calls) + 1}"
        self._surface_pane[ref] = pane_ref
        self.calls.append({"op": "new_surface_in_pane", "pane_ref": pane_ref, "name": name, "ref": ref})
        return ref

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

    def paste_text(self, ref: str, text: str) -> None:
        pass

    def list_workspaces(self) -> list[str]:
        return []

    def close(self, ref: str) -> None:
        pass


def test_persona_spawn_creates_no_obs_surface(tmp_path, monkeypatch):
    """handlers/spawn.handle creates no observer surface (issue #754).

    Per-worker observer removed. handle() spawns only the persona surface —
    zero surfaces whose name contains 'observer' or ends with ':obs'.
    """
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
        issue_number=736,
        llm="claude-code",
        multiplexer=fake_mx,
        multiplexer_mode="surface",
        dry_run=False,
        max_retries=0,
        escalation_channel=None,
        persona_llm={},
        coach_run_id=None,
        runtime_dir=str(tmp_path / ".atdd" / "runtime"),
    )
    result = spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))
    assert result == HandlerResult.HANDLED

    observer_surfaces = [
        c for c in fake_mx.calls
        if c["op"] in ("new_surface", "new_surface_in_pane", "new_workspace")
        and (
            "observer" in (c.get("name") or "").lower()
            or (c.get("name") or "").lower().endswith(":obs")
        )
    ]
    assert observer_surfaces == [], (
        f"handle() created observer surface(s) {observer_surfaces}; "
        f"issue #754: observer is coach-level, not per-worker"
    )
