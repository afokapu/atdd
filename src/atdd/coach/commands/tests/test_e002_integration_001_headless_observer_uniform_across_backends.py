# URN: test:consolidate-coach-workspace:headless-observer-in-spawn-path:E002-INTEGRATION-001-headless-observer-uniform-across-backends
# Acceptance: acc:consolidate-coach-workspace:E002-INTEGRATION-001-headless-observer-uniform-across-backends
# WMBT: wmbt:consolidate-coach-workspace:E002
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E002-INTEGRATION-001 — cmd_spawn runs the observer headless on every
multiplexer backend: one persona surface, zero ``:obs`` surfaces on cmux,
tmux, and zellij alike.

RED: ``cmd_spawn`` co-spawns the observer as a ``:obs`` surface via
``new_persona_surface`` regardless of backend. This test pins the headless
contract uniformly across the three backends.
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


class FakeBackend:
    """Multiplexer double standing in for any of cmux / tmux / zellij — only
    ``name`` identifies the backend. ``new_persona_surface`` mirrors the real
    default: persona surface + co-spawned observer ``:obs`` surface."""

    def __init__(self, backend_name: str) -> None:
        self.name = backend_name
        self.surfaces: list[str] = []
        self.persona_surface_calls = 0
        self._n = 0

    def _ref(self) -> str:
        self._n += 1
        return f"{self.name}:surface:{self._n}"

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


def _spawn_one(tmp_path: Path, monkeypatch, backend: FakeBackend) -> list:
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

    worktree = tmp_path / f"wt-{backend.name}"
    worktree.mkdir(parents=True, exist_ok=True)
    spawn.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=worktree,
        issue=745,
        agent_id="coder-745-001",
        runtime_root=tmp_path / "rt",
        multiplexer=backend,
    )
    monkeypatch.setattr(subprocess, "Popen", real_popen)
    return popen_calls


@pytest.mark.parametrize("backend_name", ["cmux", "tmux", "zellij"])
def test_headless_observer_on_backend(tmp_path, monkeypatch, backend_name):
    """On every backend, cmd_spawn creates one persona surface, zero ``:obs``
    surfaces, and launches the observer as a detached subprocess."""
    backend = FakeBackend(backend_name)
    popen_calls = _spawn_one(tmp_path, monkeypatch, backend)

    obs = [s for s in backend.surfaces
           if isinstance(s, str) and s.endswith(":obs")]
    assert obs == [], (
        f"[{backend_name}] cmd_spawn co-spawned observer surface(s) {obs}; "
        f"the observer must run headless on every backend"
    )
    assert len(backend.surfaces) == 1, (
        f"[{backend_name}] cmd_spawn created {len(backend.surfaces)} surface(s) "
        f"({backend.surfaces}); exactly one persona surface is expected"
    )

    observer_launches = [
        c for c in popen_calls
        if (isinstance(c, (list, tuple)) and "observer" in [str(x) for x in c])
        or (isinstance(c, str) and "observer" in c)
    ]
    assert len(observer_launches) == 1, (
        f"[{backend_name}] expected one detached observer subprocess; got "
        f"{len(observer_launches)} ({popen_calls})"
    )
