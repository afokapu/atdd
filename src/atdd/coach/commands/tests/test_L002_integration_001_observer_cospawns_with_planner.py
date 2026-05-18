# URN: test:integration-hardening:coach-single-command-driver:L002-INTEGRATION-001-observer-cospawns-with-planner
# Acceptance: acc:integration-hardening:L002-INTEGRATION-001-observer-cospawns-with-planner
# WMBT: wmbt:integration-hardening:L002
# Phase: GREEN
# Layer: integration
"""L002-INTEGRATION-001 — cold-start INIT→PLANNED produces one planner surface
and starts a single coach-level MultiAgentObserver.

Issue #754 changed the model: there is no per-worker observer surface.
Instead, _execute_cold_start starts one MultiAgentObserver that watches all
agent runtime dirs. This test verifies:
  - exactly one planner persona surface created
  - no ':obs' surface created alongside the persona
  - _execute_cold_start starts and stops exactly one MultiAgentObserver
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

    def surface_to_pane(self, surface_ref: Any) -> str:
        return "pane:1"

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


class _FakeObserver:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    def start(self) -> "_FakeObserver":
        self.start_calls += 1
        return self

    def stop(self) -> None:
        self.stop_calls += 1


def test_cold_start_spawns_planner_only_no_obs_surface(tmp_path, monkeypatch):
    """coach.run([N]) cold-start creates one planner surface and no ':obs' surface."""
    from atdd.coach.commands.coach import run
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import spawn as cmd_spawn_mod
    import atdd.coach.commands.observer as obs_mod

    fake_mx = _FakeMx()
    wt = tmp_path / "wt"
    wt.mkdir()

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx)
    monkeypatch.setattr(obs_mod, "MultiAgentObserver", _FakeObserver)

    rc = run(
        issue_numbers=[650],
        dry_run=False,
        resume=None,
        multiplexer_mode="pane",
        _runtime_dir_override=tmp_path / ".atdd" / "runtime",
        _max_loop_events=0,
    )

    assert rc == 0

    spawn_calls = [c for c in fake_mx.calls if c["op"] in ("new_surface", "new_workspace")]
    assert len(spawn_calls) >= 1, (
        f"Expected at least 1 spawn call (planner persona), got {len(spawn_calls)}: {fake_mx.calls}"
    )

    observer_surface_calls = [
        c for c in spawn_calls
        if "observer" in (c.get("command") or "").lower()
        or (c.get("name") or "").lower().endswith(":obs")
    ]
    assert observer_surface_calls == [], (
        f"Per-worker ':obs' surfaces found: {observer_surface_calls}. "
        f"Issue #754: observer is coach-level, not per-worker."
    )


def test_cold_start_starts_one_coach_level_observer(tmp_path, monkeypatch):
    """_execute_cold_start starts exactly one MultiAgentObserver."""
    from atdd.coach.commands.coach import run
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import spawn as cmd_spawn_mod
    import atdd.coach.commands.observer as obs_mod

    fake_mx = _FakeMx()
    wt = tmp_path / "wt"
    wt.mkdir()

    observer_instances: list[_FakeObserver] = []

    def _make_observer(*args: Any, **kwargs: Any) -> _FakeObserver:
        obs = _FakeObserver(*args, **kwargs)
        observer_instances.append(obs)
        return obs

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx)
    monkeypatch.setattr(obs_mod, "MultiAgentObserver", _make_observer)

    run(
        issue_numbers=[650],
        dry_run=False,
        resume=None,
        multiplexer_mode="pane",
        _runtime_dir_override=tmp_path / ".atdd" / "runtime",
        _max_loop_events=0,
    )

    assert len(observer_instances) == 1, (
        f"Expected exactly 1 MultiAgentObserver, got {len(observer_instances)}"
    )
    obs = observer_instances[0]
    assert obs.start_calls == 1, (
        f"observer.start() called {obs.start_calls} times (expected 1)"
    )
    assert obs.stop_calls == 1, (
        f"observer.stop() called {obs.stop_calls} times (expected 1 — should stop after waves)"
    )
