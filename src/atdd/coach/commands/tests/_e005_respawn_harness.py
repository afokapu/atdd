"""Shared test harness for the E005 per-phase respawn RED tests (issue #746).

Not collected by pytest (no ``test_`` prefix). Provides a multiplexer double
that tracks surface creation, in-place respawns, per-surface process identity,
and renames — plus a helper that wires the coach spawn handler + ``cmd_spawn``
to that double.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-per-phase-fresh-agent-respawn` |
| Train | `none` |
| Feature | per-phase fresh agent respawn |
"""


class FakeRespawnMx:
    """Multiplexer double — tracks pane creation, in-place respawn, per-surface
    process identity, and renames.

    A *process token* is assigned on every surface creation and bumped on every
    respawn, so a test can prove each phase ran a FRESH process in the SAME
    surface.
    """

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.panes: dict[str, dict] = {}   # ref -> {"name", "live", "process"}
        self._n = 0
        self._proc = 0

    # --- surface lifecycle -------------------------------------------------
    def _add(self, name: Any, command: Any) -> str:
        self._n += 1
        self._proc += 1
        ref = f"pane:{self._n}"
        self.panes[ref] = {"name": name, "live": True, "process": self._proc}
        return ref

    def new_persona_surface(
        self, cwd: Any = None, command: Any = None, name: Any = None,
        *, observer_runtime_root: str = "", observer_agent_id: str = "",
        observer_name: str = "", observer_command: str = "", **_: Any,
    ) -> str:
        ref = self._add(name, command)
        self.calls.append(
            {"op": "new_persona_surface", "name": name, "ref": ref,
             "command": command, "process": self.panes[ref]["process"]}
        )
        return ref

    def new_surface(self, workspace_ref: Any = None, pane_ref: Any = None,
                    cwd: Any = None, command: Any = None, name: Any = None,
                    direction: Any = None) -> str:
        ref = self._add(name, command)
        self.calls.append(
            {"op": "new_surface", "name": name, "ref": ref,
             "command": command, "process": self.panes[ref]["process"]}
        )
        return ref

    def new_workspace(self, cwd: Any = None, command: Any = None,
                      name: Optional[str] = None) -> str:
        ref = self._add(name, command)
        self.calls.append(
            {"op": "new_workspace", "name": name, "ref": ref,
             "command": command, "process": self.panes[ref]["process"]}
        )
        return ref

    def _respawn(self, ref: str, command: Any) -> None:
        self._proc += 1
        if ref in self.panes:
            self.panes[ref]["process"] = self._proc
        self.calls.append(
            {"op": "respawn", "ref": ref, "command": command,
             "process": self._proc}
        )

    def respawn(self, ref: str, command: Any = None, **_: Any) -> None:
        self._respawn(ref, command)

    def respawn_pane(self, ref: str, command: Any = None, **_: Any) -> None:
        self._respawn(ref, command)

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})
        if ref in self.panes:
            self.panes[ref]["name"] = name

    def close(self, ref: str) -> None:
        self.calls.append({"op": "close", "ref": ref})
        if ref in self.panes:
            self.panes[ref]["live"] = False

    # --- io ----------------------------------------------------------------
    def send(self, ref: str, text: str) -> None:
        self.calls.append({"op": "send", "ref": ref, "text": text})

    def send_key(self, ref: str, key: str) -> None:
        self.calls.append({"op": "send_key", "ref": ref, "key": key})

    def paste_text(self, ref: str, text: str) -> None:
        self.calls.append({"op": "paste_text", "ref": ref, "text": text})

    def read_screen(self, ref: str, lines: int = 50) -> str:
        return ""

    def list_panes(self) -> list[dict]:
        return [
            {"ref": ref, "name": p["name"]}
            for ref, p in self.panes.items() if p["live"]
        ]

    def list_workspaces(self) -> list[str]:
        return [p["name"] for p in self.panes.values() if p["live"]]

    # --- test introspection ------------------------------------------------
    def ops(self, op: str) -> list[dict]:
        return [c for c in self.calls if c["op"] == op]

    def spawn_or_respawn_calls(self) -> list[dict]:
        kinds = {"new_persona_surface", "new_surface", "new_workspace", "respawn"}
        return [c for c in self.calls if c["op"] in kinds]

    def texts_sent(self) -> list[str]:
        return [
            c.get("text", "") for c in self.calls
            if c["op"] in ("send", "paste_text", "send_key")
        ]


def patch_spawn_env(tmp_path, monkeypatch, fake_mx, *, repo_short: str = "ATDD"):
    """Wire the spawn handler + ``cmd_spawn`` to ``fake_mx``. Returns the
    ``spawn`` handler module."""
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import spawn as cmd_spawn_mod, session_template

    worktree = tmp_path / "feat-coach-per-phase-fresh-agent-respawn"
    worktree.mkdir(exist_ok=True)
    runtime_root = tmp_path / ".atdd" / "runtime"

    monkeypatch.setattr(
        spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt"
    )
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: worktree)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(
        cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx
    )
    monkeypatch.setattr(
        cmd_spawn_mod, "compute_repo_short_name",
        lambda config: repo_short, raising=False,
    )
    monkeypatch.setattr(
        session_template, "fetch_issue",
        lambda n: {"number": n, "title": "per-phase fresh agent respawn",
                   "body": SAMPLE_BODY},
    )
    return spawn_handler
