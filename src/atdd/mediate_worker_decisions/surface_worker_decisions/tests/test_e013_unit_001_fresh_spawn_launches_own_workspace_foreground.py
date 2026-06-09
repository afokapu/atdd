# URN: test:mediate-worker-decisions:surface-worker-decisions:E013-UNIT-001-fresh-spawn-launches-own-workspace-foreground
# Acceptance: acc:mediate-worker-decisions:E013-UNIT-001-fresh-spawn-launches-own-workspace-foreground
# WMBT: wmbt:mediate-worker-decisions:E013
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E013-UNIT-001 — a fresh dispatch spawn launches an own-workspace foreground.

The proven-publishing launch shape (the #1007 daemon launcher + the
surface_worker_decisions live smoke) runs the agent as the foreground process of
its OWN cmux workspace (`cmux new-workspace --command`). A fresh dispatch worker
spawn must use that shape — NOT `new-surface --pane <coach>` + a `cmux send`
text-paste, which leaves the worker in the coach's workspace and the wrapper Feed
hook un-fired.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from atdd.coach.commands.spawn import _create_surface


class _RecordingBackend:
    name = "fake"

    def __init__(self) -> None:
        self.calls: List[dict] = []

    def resolve_focused_pane(self, workspace: Optional[str] = None) -> str:
        return "pane:1"

    def new_surface_in_pane(
        self, pane_ref: str, cwd: Any = None, command: Any = None, name: Any = None
    ) -> str:
        self.calls.append({"op": "new_surface_in_pane", "command": command})
        return "surface:pasted"

    def new_worker_surface_in_own_workspace(
        self, cwd: Any = None, command: Any = None, name: Any = None
    ) -> str:
        self.calls.append({"op": "new_worker_workspace", "command": command, "cwd": cwd})
        return "surface:own"


def test_fresh_spawn_uses_own_workspace_foreground_launch(tmp_path: Path):
    backend = _RecordingBackend()
    agent_cmd = 'claude "go" --permission-mode acceptEdits --allowedTools "Read"'

    _create_surface(backend, worktree=tmp_path, command=agent_cmd, name="ATDD1025")

    ops = [c["op"] for c in backend.calls]
    assert "new_worker_workspace" in ops  # own-workspace foreground launch
    assert "new_surface_in_pane" not in ops  # NOT a send-paste into the coach pane
    own = next(c for c in backend.calls if c["op"] == "new_worker_workspace")
    assert own["command"] == agent_cmd  # the agent IS the workspace foreground
