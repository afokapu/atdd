# URN: test:integration-hardening:coach-single-command-driver:L002-INTEGRATION-001-observer-cospawns-with-planner
# Acceptance: acc:integration-hardening:L002-INTEGRATION-001-observer-cospawns-with-planner
# WMBT: wmbt:integration-hardening:L002
# Phase: RED
# Layer: integration
"""L002-INTEGRATION-001 — cold-start INIT→PLANNED produces planner + observer surfaces.

coach.run([N]) without --resume must produce exactly 2 spawn calls via
FakeMultiplexer: one for the planner persona and one for the observer sidecar.
This is the integration-level counterpart to L002-UNIT-001.
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
        ref = f"surface:{len(self.calls) + 1}"
        self.calls.append({"op": "new_surface", "cwd": cwd, "command": command, "name": name, "ref": ref})
        return ref

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


def test_cold_start_spawns_planner_and_observer(tmp_path, monkeypatch):
    """coach.run([N]) cold-start records both planner and observer spawns."""
    from atdd.coach.commands.coach import run
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import spawn as cmd_spawn_mod

    fake_mx = _FakeMx()
    wt = tmp_path / "wt"
    wt.mkdir()

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx)

    rc = run(
        issue_numbers=[650],
        dry_run=False,
        resume=None,
        _runtime_dir_override=tmp_path / ".atdd" / "runtime",
        _max_loop_events=0,
    )

    assert rc == 0

    spawn_calls = [c for c in fake_mx.calls if c["op"] in ("new_surface", "new_workspace")]
    assert len(spawn_calls) >= 2, (
        f"Expected at least 2 spawn calls (persona + observer), got {len(spawn_calls)}: {fake_mx.calls}"
    )

    planner_calls = [c for c in spawn_calls if "planner" in (c.get("command") or "")]
    assert len(planner_calls) >= 1, (
        f"Expected at least 1 planner spawn; calls={spawn_calls}"
    )

    observer_calls = [c for c in spawn_calls if "observer" in (c.get("command") or "")]
    assert len(observer_calls) >= 1, (
        f"Expected at least 1 observer spawn call; calls={spawn_calls}"
    )
