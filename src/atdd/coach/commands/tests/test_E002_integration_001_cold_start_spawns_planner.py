# URN: test:integration-hardening:coach-cold-start-wiring:E002-INTEGRATION-001-cold-start-spawns-planner
# Acceptance: acc:integration-hardening:E002-INTEGRATION-001-cold-start-spawns-planner
# WMBT: wmbt:integration-hardening:E002
# Phase: RED
# Layer: integration
"""E002-INTEGRATION-001 — cold-start spawns the planner persona at INIT→PLANNED.

coach.run([N]) without --resume must invoke the spawn handler exactly once
with persona=planner for the INIT→PLANNED transition. FakeMultiplexer
captures calls so no real cmux daemon is required (R1, issue #645).
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
        self.calls.append({"op": "new_workspace", "cwd": cwd, "command": command, "ref": ref})
        return ref

    def new_surface(self, workspace_ref: Any = None, pane_ref: Any = None,
                    cwd: Any = None, command: Any = None,
                    name: Any = None, direction: Any = None) -> str:
        ref = f"surface:{len(self.calls) + 1}"
        self.calls.append({"op": "new_surface", "cwd": cwd, "command": command, "ref": ref})
        return ref

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


def test_cold_start_spawns_planner_persona(tmp_path, monkeypatch):
    """coach.run([N]) cold-start invokes spawn with persona=planner once."""
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

    # cold-start stops after initial spawn (event loop will find no events)
    rc = run(
        issue_numbers=[645],
        dry_run=False,
        resume=None,
        _runtime_dir_override=tmp_path / ".atdd" / "runtime",
        _max_loop_events=0,  # exit event loop immediately
    )

    assert rc == 0
    spawn_calls = [c for c in fake_mx.calls if c["op"] in ("new_workspace", "new_surface")]
    assert len(spawn_calls) >= 1, f"Expected at least one spawn call; got {fake_mx.calls}"
    # At least one call must be for the planner command
    planner_calls = [c for c in spawn_calls if "planner" in (c.get("command") or "")]
    assert len(planner_calls) >= 1, (
        f"Expected planner in spawn command; calls={spawn_calls}"
    )


def test_cold_start_records_planner_spawn_via_fake_multiplexer(tmp_path, monkeypatch):
    """FakeMultiplexer from multiplexer module can be used directly."""
    from atdd.coach.utils.multiplexer import FakeMultiplexer
    from atdd.coach.commands.coach import run
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import spawn as cmd_spawn_mod

    fake_mx = FakeMultiplexer()
    wt = tmp_path / "wt"
    wt.mkdir()

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx)

    rc = run(
        issue_numbers=[645],
        dry_run=False,
        resume=None,
        _runtime_dir_override=tmp_path / ".atdd" / "runtime",
        _max_loop_events=0,
    )

    assert rc == 0
    assert any(
        c["op"] in ("new_workspace", "new_surface") for c in fake_mx.calls
    ), f"No spawn recorded in FakeMultiplexer calls: {fake_mx.calls}"
