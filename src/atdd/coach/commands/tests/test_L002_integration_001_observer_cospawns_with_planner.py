# URN: test:integration-hardening:coach-single-command-driver:L002-INTEGRATION-001-observer-cospawns-with-planner
# Acceptance: acc:integration-hardening:L002-INTEGRATION-001-observer-cospawns-with-planner
# WMBT: wmbt:integration-hardening:L002
# Phase: RED
# Layer: integration
"""L002-INTEGRATION-001 — cold-start INIT→PLANNED produces a planner surface
and a headless observer.

coach.run([N]) without --resume must spawn the planner persona surface and
launch its observer sidecar. Issue #745: the observer no longer co-spawns as
a multiplexer surface — it runs HEADLESS via ``subprocess.Popen`` (`atdd
observer run`), mirroring ``handlers/spawn.py::_spawn_observer`` (#736). This
test pins that contract: a planner surface on the multiplexer + a detached
observer subprocess.
"""
from __future__ import annotations

import subprocess
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


class _DummyProc:
    pid = 4242
    args: list = []
    returncode = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def communicate(self, *a, **k):
        return ("", "")

    def wait(self, *a, **k):
        return 0

    def poll(self, *a, **k):
        return None


def _is_observer_cmd(cmd: Any) -> bool:
    if isinstance(cmd, (list, tuple)):
        return "observer" in [str(x) for x in cmd]
    return isinstance(cmd, str) and "observer" in cmd


def test_cold_start_spawns_planner_and_observer(tmp_path, monkeypatch):
    """coach.run([N]) cold-start spawns the planner surface and launches the
    observer headless (detached subprocess, no `:obs` surface)."""
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

    # Issue #745: the observer launches headless via subprocess.Popen. Spy
    # only the observer launch; delegate every other subprocess to the real
    # Popen so the coach run path is unaffected.
    popen_calls: list = []
    real_popen = subprocess.Popen

    def _spy_popen(cmd: Any, *a: Any, **k: Any):
        if _is_observer_cmd(cmd):
            popen_calls.append(cmd)
            return _DummyProc()
        return real_popen(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "Popen", _spy_popen)

    rc = run(
        issue_numbers=[650],
        dry_run=False,
        resume=None,
        multiplexer_mode="pane",
        _runtime_dir_override=tmp_path / ".atdd" / "runtime",
        _max_loop_events=0,
    )

    assert rc == 0

    # The planner persona is placed as exactly one multiplexer surface.
    spawn_calls = [c for c in fake_mx.calls if c["op"] in ("new_surface", "new_workspace")]
    assert len(spawn_calls) >= 1, (
        f"Expected the planner persona placed as a multiplexer surface; "
        f"calls={fake_mx.calls}"
    )

    # The observer co-spawns with it — headless, as a detached subprocess.
    # Its agent-id is derived from the planner agent-id, so the launch argv
    # carries `planner`, proving the planner's observer (not some other).
    observer_launches = [c for c in popen_calls if _is_observer_cmd(c)]
    assert len(observer_launches) >= 1, (
        f"Expected the observer launched headless via subprocess.Popen "
        f"(`atdd observer run`); popen_calls={popen_calls}"
    )
    planner_observer = [
        c for c in observer_launches
        if (isinstance(c, (list, tuple)) and any("planner" in str(x) for x in c))
        or (isinstance(c, str) and "planner" in c)
    ]
    assert len(planner_observer) >= 1, (
        f"Expected the planner's observer launched headless; "
        f"observer launches={observer_launches}"
    )

    # No observer `:obs` multiplexer surface — the observer is headless.
    obs_surfaces = [
        c for c in spawn_calls
        if (c.get("name") or "").endswith(":obs")
        or "observer" in (c.get("command") or "")
    ]
    assert obs_surfaces == [], (
        f"Observer co-spawned as a multiplexer surface {obs_surfaces}; it must "
        f"run headless with no surface"
    )
