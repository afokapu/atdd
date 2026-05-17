# URN: test:consolidate-coach-workspace:wire-layout-into-spawn-path:E002-INTEGRATION-002-layout-holds-across-all-three-backends
# Acceptance: acc:consolidate-coach-workspace:E002-INTEGRATION-002-layout-holds-across-all-three-backends
# WMBT: wmbt:consolidate-coach-workspace:E002
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E002-INTEGRATION-002 — the wired spawn path produces one right pane with N
surfaces on every multiplexer backend, using only the abstraction's
surface/tab primitive.

RED: ``cmd_spawn`` opens a tiled pane per worker regardless of backend. This
test pins the contract across cmux, tmux, and zellij: workers resolve to one
right pane of surfaces, and the spawn path issues no raw ``cmux`` command — it
goes only through the ``Multiplexer`` abstraction.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]


_SURFACE_OPS = ("new_surface",)
_TILED_PANE_OPS = ("new_persona_surface", "new_pane", "split_pane")

SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-workspace-layout-not-wired-into-spawn-path` |
| Train | none |
| Feature | wire layout into spawn path |
"""


class FakeBackend:
    """Multiplexer double standing in for any of cmux / tmux / zellij — the
    surface/tab primitive is uniform, only ``name`` identifies the backend."""

    def __init__(self, backend_name: str) -> None:
        self.name = backend_name
        self.calls: list[dict] = []
        self._n = 0

    def _rec(self, op: str, name: Any = None) -> str:
        self._n += 1
        ref = f"{self.name}:{op}:{self._n}"
        self.calls.append({"op": op, "name": name, "ref": ref})
        return ref

    def new_workspace(self, cwd: Any = None, command: Any = None,
                      name: Optional[str] = None) -> str:
        return self._rec("new_workspace", name)

    def new_surface(self, workspace_ref: Any = None, pane_ref: Any = None,
                    cwd: Any = None, command: Any = None, name: Any = None,
                    direction: Any = None) -> str:
        return self._rec("new_surface", name)

    def new_persona_surface(self, cwd: Any = None, command: Any = None,
                            name: Any = None, **_: Any) -> str:
        return self._rec("new_persona_surface", name)

    def new_pane(self, *a: Any, **k: Any) -> str:
        return self._rec("new_pane")

    def split_pane(self, *a: Any, **k: Any) -> str:
        return self._rec("split_pane")

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})

    def send(self, ref: str, text: str) -> None:
        self.calls.append({"op": "send", "ref": ref, "text": text})

    def send_key(self, ref: str, key: str) -> None:
        self.calls.append({"op": "send_key", "ref": ref, "key": key})

    def paste_text(self, ref: str, text: str) -> None:
        self.calls.append({"op": "paste_text", "ref": ref})

    def read_screen(self, ref: str, lines: int = 50) -> str:
        return ""

    def list_panes(self) -> list[dict]:
        return [{"name": c["name"], "ref": c["ref"]}
                for c in self.calls if c["op"] == "new_workspace"]

    def count(self, *ops: str) -> int:
        return sum(1 for c in self.calls if c["op"] in ops)


def _spawn(tmp_path: Path, monkeypatch, backend: FakeBackend, issue: int) -> dict:
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

    worktree = tmp_path / f"wt-{backend.name}-{issue}"
    worktree.mkdir(parents=True, exist_ok=True)
    return spawn.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=worktree,
        issue=issue,
        agent_id=f"coder-{issue}-001",
        runtime_root=tmp_path / "rt",
        multiplexer=backend,
    )


@pytest.mark.parametrize("backend_name", ["cmux", "tmux", "zellij"])
def test_layout_holds_across_backend(tmp_path, monkeypatch, backend_name):
    """On every backend, three workers resolve to one right pane of three
    surfaces and the spawn path issues no raw ``cmux`` command."""
    import subprocess

    argv_seen: list[Any] = []
    real_run, real_popen = subprocess.run, subprocess.Popen

    def _run(cmd: Any, *a: Any, **k: Any):
        argv_seen.append(cmd)
        return real_run(cmd, *a, **k)

    def _popen(cmd: Any, *a: Any, **k: Any):
        argv_seen.append(cmd)
        return real_popen(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", _run)
    monkeypatch.setattr(subprocess, "Popen", _popen)

    backend = FakeBackend(backend_name)
    issues = [736, 601, 745]
    for issue in issues:
        _spawn(tmp_path, monkeypatch, backend, issue)

    surfaces = backend.count(*_SURFACE_OPS)
    assert surfaces == len(issues), (
        f"[{backend_name}] expected {len(issues)} worker surfaces; got "
        f"{surfaces} — workers not added via the surface/tab primitive"
    )
    tiled = backend.count(*_TILED_PANE_OPS)
    assert tiled == 0, (
        f"[{backend_name}] spawn path opened {tiled} tiled pane(s); workers "
        f"must resolve to one right pane of surfaces on every backend"
    )
    assert backend.count("new_workspace") == 1, (
        f"[{backend_name}] expected exactly one resolve-or-created right pane; "
        f"got {backend.count('new_workspace')}"
    )

    def _is_cmux(cmd: Any) -> bool:
        if isinstance(cmd, (list, tuple)) and cmd:
            return str(cmd[0]).split("/")[-1] == "cmux"
        if isinstance(cmd, str):
            return cmd.strip().split()[0:1] == ["cmux"]
        return False

    raw_cmux = [c for c in argv_seen if _is_cmux(c)]
    assert raw_cmux == [], (
        f"[{backend_name}] spawn path issued raw cmux command(s) {raw_cmux} — "
        f"placement must go only through the Multiplexer abstraction"
    )
