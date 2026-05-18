# URN: test:consolidate-coach-workspace:headless-observer-in-spawn-path:E002-UNIT-001-cmd-spawn-runs-observer-headless
# Acceptance: acc:consolidate-coach-workspace:E002-UNIT-001-cmd-spawn-runs-observer-headless
# WMBT: wmbt:consolidate-coach-workspace:E002
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""E002-UNIT-001 — a single real ``cmd_spawn`` invocation creates exactly one
surface, no ``:obs`` surface, and starts the observer as a detached
background subprocess.

RED: ``cmd_spawn`` routes through ``_create_surface`` → ``new_persona_surface``,
which co-spawns the observer as a visible ``<issue>:obs`` multiplexer surface —
so every issue is two tabs. #736 made ``handlers/spawn.py::_spawn_observer``
headless but never touched ``cmd_spawn``. This test pins the headless contract
for ``cmd_spawn``: one persona surface, no ``:obs`` tab, observer via
``subprocess.Popen``.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]


SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-workspace-layout-not-wired-into-spawn-path` |
| Train | none |
| Feature | headless observer in spawn path |
"""


class FakeMx:
    """Multiplexer double — records every surface creation by name.

    ``new_persona_surface`` mirrors the real default: it co-spawns a persona
    surface *and* an observer ``:obs`` surface."""

    name = "fake"

    def __init__(self) -> None:
        self.surfaces: list[str] = []          # names of created surfaces
        self.persona_surface_calls = 0
        self._n = 0

    def _ref(self) -> str:
        self._n += 1
        return f"surface:{self._n}"

    def new_workspace(self, cwd: Any = None, command: Any = None,
                      name: Optional[str] = None) -> str:
        self.surfaces.append(name)
        return self._ref()

    def new_surface(self, workspace_ref: Any = None, pane_ref: Any = None,
                    cwd: Any = None, command: Any = None, name: Any = None,
                    direction: Any = None) -> str:
        self.surfaces.append(name)
        return self._ref()

    def new_persona_surface(self, cwd: Any = None, command: Any = None,
                            name: Any = None, observer_name: str = "",
                            **_: Any) -> str:
        self.persona_surface_calls += 1
        persona_ref = self._ref()
        self.surfaces.append(name)
        if observer_name:
            self.surfaces.append(observer_name)
        return persona_ref

    def rename(self, ref: str, name: str) -> None:
        pass

    def send(self, ref: str, text: str) -> None:
        pass

    def send_key(self, ref: str, key: str) -> None:
        pass

    def paste_text(self, ref: str, text: str) -> None:
        pass

    def read_screen(self, ref: str, lines: int = 50) -> str:
        return ""


def _spawn_one(tmp_path: Path, monkeypatch, fake_mx: FakeMx) -> tuple[dict, list]:
    """Drive the real ``cmd_spawn`` for one persona; return (result, popen_calls)."""
    from atdd.coach.commands import spawn
    from atdd.coach.commands import session_template

    monkeypatch.setattr(
        session_template, "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": SAMPLE_BODY},
    )
    monkeypatch.setattr(spawn, "compute_repo_short_name",
                        lambda config: "ATDD", raising=False)
    monkeypatch.setattr(spawn, "load_atdd_config",
                        lambda root: {"repo": {"short_name": "ATDD"}},
                        raising=False)
    monkeypatch.setattr(spawn, "capture_session_uuid",
                        lambda **kw: None, raising=False)

    popen_calls: list = []
    real_popen = subprocess.Popen

    class _DummyProc:
        pid = 4242

    def _spy_popen(cmd: Any, *a: Any, **k: Any):
        popen_calls.append(cmd)
        return _DummyProc()

    monkeypatch.setattr(subprocess, "Popen", _spy_popen)

    worktree = tmp_path / "wt-745"
    worktree.mkdir(exist_ok=True)
    result = spawn.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=worktree,
        issue=745,
        agent_id="coder-745-001",
        runtime_root=tmp_path / "rt",
        multiplexer=fake_mx,
    )
    monkeypatch.setattr(subprocess, "Popen", real_popen)
    return result, popen_calls


def test_cmd_spawn_creates_exactly_one_surface_no_obs(tmp_path, monkeypatch):
    """cmd_spawn creates one persona surface and no ``:obs`` surface."""
    fake_mx = FakeMx()
    _spawn_one(tmp_path, monkeypatch, fake_mx)

    obs = [s for s in fake_mx.surfaces if isinstance(s, str) and s.endswith(":obs")]
    assert obs == [], (
        f"cmd_spawn co-spawned observer surface(s) {obs} — the observer must "
        f"run headless with no `:obs` multiplexer surface (RED)"
    )
    assert len(fake_mx.surfaces) == 1, (
        f"cmd_spawn created {len(fake_mx.surfaces)} surface(s) "
        f"({fake_mx.surfaces}); spawning one issue must create exactly one "
        f"surface (the persona only)"
    )


def test_cmd_spawn_starts_observer_as_detached_subprocess(tmp_path, monkeypatch):
    """cmd_spawn launches the observer via exactly one ``subprocess.Popen``."""
    fake_mx = FakeMx()
    _, popen_calls = _spawn_one(tmp_path, monkeypatch, fake_mx)

    observer_launches = [
        c for c in popen_calls
        if (isinstance(c, (list, tuple)) and "observer" in [str(x) for x in c])
        or (isinstance(c, str) and "observer" in c)
    ]
    assert len(observer_launches) == 1, (
        f"expected exactly one detached observer subprocess; got "
        f"{len(observer_launches)} ({popen_calls}) — cmd_spawn must launch "
        f"`atdd observer run` headless via subprocess.Popen, not as a surface"
    )
    assert fake_mx.persona_surface_calls == 0, (
        f"cmd_spawn called new_persona_surface {fake_mx.persona_surface_calls} "
        f"time(s) — the observer-co-spawning surface primitive must no longer "
        f"be used; the observer runs headless"
    )
