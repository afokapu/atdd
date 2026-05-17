# URN: test:consolidate-coach-workspace:wire-layout-into-spawn-path:E002-UNIT-001-cmd-spawn-places-worker-via-add-worker-surface
# Acceptance: acc:consolidate-coach-workspace:E002-UNIT-001-cmd-spawn-places-worker-via-add-worker-surface
# WMBT: wmbt:consolidate-coach-workspace:E002
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""E002-UNIT-001 — a single real ``cmd_spawn`` invocation places its worker
via ``coach_workspace.add_worker_surface`` and opens zero new tiled panes.

RED: ``cmd_spawn`` still routes worker placement through ``_create_surface`` →
``new_persona_surface`` — a new tiled pane per worker. #736 shipped
``coach_workspace.add_worker_surface`` but the spawn path never imports or
calls it, so the 50/50 layout is dead code.

RED→GREEN contract: ``cmd_spawn`` must place each worker by calling
``coach_workspace.add_worker_surface`` *module-qualified* — i.e.
``from atdd.coach.commands import coach_workspace`` then
``coach_workspace.add_worker_surface(...)`` — so this spy binds and so the
module stays patchable.
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


class FakeMx:
    """Multiplexer double — records every call and separates surface (tab)
    creation from tiled-pane creation."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._n = 0

    def _rec(self, op: str, name: Any = None) -> str:
        self._n += 1
        ref = f"{op}:{self._n}"
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


def _spawn_one(tmp_path: Path, monkeypatch, fake_mx: FakeMx) -> dict:
    """Drive the real ``cmd_spawn`` for one worker against ``fake_mx``."""
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
    # capture_session_uuid sleeps 1.5s and scrapes ~/.claude — not under test.
    monkeypatch.setattr(spawn, "capture_session_uuid",
                        lambda **kw: None, raising=False)

    worktree = tmp_path / "wt-745"
    worktree.mkdir(exist_ok=True)
    return spawn.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=worktree,
        issue=745,
        agent_id="coder-745-001",
        runtime_root=tmp_path / "rt",
        multiplexer=fake_mx,
    )


def test_cmd_spawn_places_worker_via_add_worker_surface(tmp_path, monkeypatch):
    """The real ``cmd_spawn`` places its worker through
    ``coach_workspace.add_worker_surface`` and opens no tiled pane."""
    from atdd.coach.commands import coach_workspace

    add_worker_calls: list[tuple] = []
    real_add_worker = coach_workspace.add_worker_surface

    def _spy(*a: Any, **k: Any) -> Any:
        add_worker_calls.append((a, k))
        return real_add_worker(*a, **k)

    monkeypatch.setattr(coach_workspace, "add_worker_surface", _spy)

    fake_mx = FakeMx()
    _spawn_one(tmp_path, monkeypatch, fake_mx)

    assert len(add_worker_calls) >= 1, (
        "cmd_spawn did not call coach_workspace.add_worker_surface — the "
        "worker is still placed as a tiled pane; #736's layout module is "
        "dead code in the spawn path (RED)"
    )
    assert fake_mx.count(*_TILED_PANE_OPS) == 0, (
        f"cmd_spawn opened {fake_mx.count(*_TILED_PANE_OPS)} tiled pane(s) "
        f"({[c['op'] for c in fake_mx.calls if c['op'] in _TILED_PANE_OPS]}); "
        f"a worker must be a surface in the right pane, never a new pane"
    )
    assert fake_mx.count(*_SURFACE_OPS) >= 1, (
        "cmd_spawn created no worker surface — the worker was not placed via "
        "add_worker_surface's new_surface call"
    )


def test_cmd_spawn_makes_no_raw_cmux_subprocess(tmp_path, monkeypatch):
    """Worker placement goes through the Multiplexer abstraction — cmd_spawn
    shells out to no raw ``cmux`` command."""
    import subprocess

    argv_seen: list[Any] = []
    real_run = subprocess.run
    real_popen = subprocess.Popen

    def _run(cmd: Any, *a: Any, **k: Any):
        argv_seen.append(cmd)
        return real_run(cmd, *a, **k)

    def _popen(cmd: Any, *a: Any, **k: Any):
        argv_seen.append(cmd)
        return real_popen(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", _run)
    monkeypatch.setattr(subprocess, "Popen", _popen)

    fake_mx = FakeMx()
    _spawn_one(tmp_path, monkeypatch, fake_mx)

    def _is_cmux(cmd: Any) -> bool:
        if isinstance(cmd, (list, tuple)) and cmd:
            return str(cmd[0]).split("/")[-1] == "cmux"
        if isinstance(cmd, str):
            return cmd.strip().split()[0:1] == ["cmux"]
        return False

    raw_cmux = [c for c in argv_seen if _is_cmux(c)]
    assert raw_cmux == [], (
        f"spawn path issued raw cmux command(s) {raw_cmux} — placement must "
        f"go through the Multiplexer abstraction so it holds on tmux/zellij too"
    )
