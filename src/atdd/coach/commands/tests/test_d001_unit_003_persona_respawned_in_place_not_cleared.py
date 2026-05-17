# URN: test:coach-wave-orchestration:within-wave-concurrency-and-pane-identity:D001-UNIT-003-persona-respawned-in-place-not-cleared
# Acceptance: acc:coach-wave-orchestration:D001-UNIT-003-persona-respawned-in-place-not-cleared
# WMBT: wmbt:coach-wave-orchestration:D001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""D001-UNIT-003 — a phase transition relaunches the persona agent in place via
``cmux respawn-pane`` (a fresh process), and ``/clear`` is not used.

RED: ``handlers/spawn.py`` spawns a brand-new pane each phase and never issues a
respawn-pane. This test pins the in-place respawn — a fresh ``claude`` process
inside the issue's existing surface, not a ``/clear`` conversation reset.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Phase, Transition

pytestmark = [pytest.mark.platform]


SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-within-wave-serial-execution` |
| Train | `none` |
| Feature | persistent issue pane |
"""


class FakeCmuxMx:
    """cmux-style multiplexer double — tracks pane creation and respawn calls."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.panes: dict[str, dict] = {}        # ref -> {"name", "live"}
        self._n = 0

    def _add(self, name: Any) -> str:
        self._n += 1
        ref = f"pane:{self._n}"
        self.panes[ref] = {"name": name, "live": True}
        return ref

    def new_persona_surface(
        self, cwd: Any = None, command: Any = None, name: Any = None,
        *, observer_runtime_root: str = "", observer_agent_id: str = "",
        observer_name: str = "", observer_command: str = "", **_: Any,
    ) -> str:
        ref = self._add(name)
        self.calls.append({"op": "new_persona_surface", "name": name, "ref": ref})
        return ref

    def new_surface(self, workspace_ref: Any = None, pane_ref: Any = None,
                    cwd: Any = None, command: Any = None, name: Any = None,
                    direction: Any = None) -> str:
        ref = self._add(name)
        self.calls.append({"op": "new_surface", "name": name, "ref": ref})
        return ref

    def new_workspace(self, cwd: Any = None, command: Any = None,
                      name: Optional[str] = None) -> str:
        ref = self._add(name)
        self.calls.append({"op": "new_workspace", "name": name, "ref": ref})
        return ref

    def respawn(self, ref: str, command: Any = None, **_: Any) -> None:
        self.calls.append({"op": "respawn", "ref": ref, "command": command})

    def respawn_pane(self, ref: str, command: Any = None, **_: Any) -> None:
        self.calls.append({"op": "respawn", "ref": ref, "command": command})

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})
        if ref in self.panes:
            self.panes[ref]["name"] = name

    def close(self, ref: str) -> None:
        self.calls.append({"op": "close", "ref": ref})
        if ref in self.panes:
            self.panes[ref]["live"] = False

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
    def respawns(self) -> list[dict]:
        return [c for c in self.calls if c["op"] == "respawn"]

    def texts_sent(self) -> list[str]:
        return [
            c.get("text", "") for c in self.calls
            if c["op"] in ("send", "paste_text")
        ]


def _patch_spawn_env(tmp_path, monkeypatch, fake_mx):
    """Wire the spawn handler + cmd_spawn to the fake multiplexer."""
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import spawn as cmd_spawn_mod, session_template

    worktree = tmp_path / "feat-coach-within-wave-serial-execution"
    worktree.mkdir(exist_ok=True)
    runtime_root = tmp_path / ".atdd" / "runtime"

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: worktree)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx)
    monkeypatch.setattr(
        cmd_spawn_mod, "compute_repo_short_name", lambda config: "ATDD", raising=False
    )
    monkeypatch.setattr(
        session_template, "fetch_issue",
        lambda n: {"number": n, "title": "persistent issue pane", "body": SAMPLE_BODY},
    )
    return spawn_handler


def test_persona_respawned_in_place_not_cleared(tmp_path, monkeypatch):
    """The next phase respawns the persona in place; /clear is never sent."""
    fake_mx = FakeCmuxMx()
    spawn_handler = _patch_spawn_env(tmp_path, monkeypatch, fake_mx)

    ctx = CoachContext(issue_number=730, multiplexer_mode="pane")

    # Prior phase: the issue's persistent surface is created with the planner.
    r1 = spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))
    assert r1 == HandlerResult.HANDLED
    assert fake_mx.panes, "first phase created no surface"
    surface_ref = next(iter(fake_mx.panes))

    # Next phase: the tester persona is respawned inside that same surface.
    r2 = spawn_handler.handle(ctx, Transition(src=Phase.PLANNED, dst=Phase.RED))
    assert r2 == HandlerResult.HANDLED

    respawns = fake_mx.respawns()
    assert respawns, (
        "the phase transition issued no respawn-pane — a new pane was spawned "
        "instead of relaunching the persona agent in place"
    )
    # The respawn targets the issue's existing surface and carries a command.
    assert any(c["ref"] == surface_ref for c in respawns), (
        f"respawn did not target the issue's surface {surface_ref}: {respawns}"
    )
    assert any(c.get("command") for c in respawns), (
        f"respawn carried no persona launch command: {respawns}"
    )
    # No /clear was sent — a fresh process is started, not a conversation reset.
    assert not any("/clear" in t for t in fake_mx.texts_sent()), (
        f"/clear was sent to the surface: {fake_mx.texts_sent()}"
    )
