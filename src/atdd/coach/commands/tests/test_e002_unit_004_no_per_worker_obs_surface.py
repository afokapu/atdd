# URN: test:observe-and-correct:observer-runtime-and-rules:E002-UNIT-004-no-per-worker-obs-surface
# Acceptance: acc:observe-and-correct:E002-UNIT-004-no-per-worker-obs-surface
# WMBT: wmbt:observe-and-correct:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E002-UNIT-004 — cmd_spawn and handlers/spawn.handle create no ':obs'
multiplexer surface for any worker.

RED: cmd_spawn currently calls new_persona_surface which creates an ':obs'
surface alongside every worker. handlers/spawn.handle calls _spawn_observer
which starts a subprocess. Both must be removed.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from atdd.coach.utils.multiplexer import FakeMultiplexer

pytestmark = [pytest.mark.platform]


def _all_surface_names(calls: list[dict]) -> list[str]:
    return [c.get("name", "") for c in calls if c.get("op") in ("new_surface", "new_surface_in_pane")]


def test_cmd_spawn_pane_mode_creates_no_obs_surface(tmp_path, monkeypatch):
    """cmd_spawn(multiplexer_mode='pane') creates no ':obs' surface."""
    from atdd.coach.commands import spawn as cmd_spawn_mod, session_template
    from atdd.coach.utils import config as cfg_mod

    wt = tmp_path / "wt"
    wt.mkdir()
    rt = tmp_path / ".atdd" / "runtime"
    rt.mkdir(parents=True, exist_ok=True)

    fake_mx = FakeMultiplexer()

    monkeypatch.setattr(session_template, "fetch_issue", lambda n: {"number": n, "title": "t", "body": ""})
    monkeypatch.setattr(session_template, "render", lambda ctx: "# prompt")
    monkeypatch.setattr(cfg_mod, "load_atdd_config", lambda p: {})
    monkeypatch.setattr("atdd.coach.commands.spawn.compute_repo_short_name", lambda cfg: "atdd")
    monkeypatch.setattr("atdd.coach.commands.spawn._build_arch_section", lambda *a, **k: "")
    monkeypatch.setattr("atdd.coach.commands.spawn._resolve_multiplexer", lambda preferred=None: fake_mx)
    monkeypatch.setattr("atdd.coach.commands.spawn.apply_canonical_name_and_layout", lambda **k: None)
    monkeypatch.setattr("atdd.coach.commands.spawn.capture_session_uuid", lambda *a, **k: None)

    cmd_spawn_mod.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=wt,
        issue=754,
        agent_id="coder-754-abc",
        runtime_root=rt,
        multiplexer_mode="pane",
        multiplexer=fake_mx,
    )

    names = _all_surface_names(fake_mx.calls)
    obs_surfaces = [n for n in names if isinstance(n, str) and (":obs" in n or "observer" in n.lower())]
    assert obs_surfaces == [], (
        f"cmd_spawn (pane mode) created ':obs' surfaces {obs_surfaces}; "
        f"all surface names: {names}"
    )


def test_spawn_handler_workspace_mode_calls_no_spawn_observer(tmp_path, monkeypatch):
    """handlers/spawn.handle in workspace mode calls _spawn_observer zero times."""
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.handlers.state_machine import CoachContext, Phase, Transition
    from atdd.coach.commands import spawn as cmd_spawn_mod

    wt = tmp_path / "wt"
    wt.mkdir()
    rt = tmp_path / ".atdd" / "runtime"
    rt.mkdir(parents=True, exist_ok=True)
    fake_mx = FakeMultiplexer()

    observer_popen_calls: list = []
    original_popen = subprocess.Popen

    def _track_popen(args: Any, *a: Any, **k: Any):
        cmd = list(args) if hasattr(args, "__iter__") and not isinstance(args, str) else [args]
        if "observer" in " ".join(str(x) for x in cmd):
            observer_popen_calls.append(cmd)
        return original_popen(["true"], **{kk: vv for kk, vv in k.items() if kk in ("stdout", "stderr", "stdin", "start_new_session")})

    monkeypatch.setattr(subprocess, "Popen", _track_popen)
    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "prompt")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", rt)
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx)

    ctx = CoachContext(
        issue_number=754,
        llm="claude-code",
        multiplexer_mode="workspace",
        dry_run=False,
        max_retries=0,
    )

    spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))

    assert observer_popen_calls == [], (
        f"handlers/spawn.handle spawned observer subprocess(es): {observer_popen_calls}; "
        f"expected 0 — the single coach-level observer is started by _execute_cold_start, not per worker"
    )

    names = _all_surface_names(fake_mx.calls)
    obs_surfaces = [n for n in names if isinstance(n, str) and (":obs" in n or "observer" in n.lower())]
    assert obs_surfaces == [], (
        f"handlers/spawn.handle created ':obs' surfaces {obs_surfaces}; expected none"
    )
