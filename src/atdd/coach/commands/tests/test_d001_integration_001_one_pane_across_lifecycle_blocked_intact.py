# URN: test:coach-wave-orchestration:within-wave-concurrency-and-pane-identity:D001-INTEGRATION-001-one-pane-across-lifecycle-blocked-intact
# Acceptance: acc:coach-wave-orchestration:D001-INTEGRATION-001-one-pane-across-lifecycle-blocked-intact
# WMBT: wmbt:coach-wave-orchestration:D001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""D001-INTEGRATION-001 — driving one issue across multiple phase transitions
keeps exactly one pane (surface ``ATDD<N>``); a BLOCKED phase leaves it intact.

RED: ``handlers/spawn.py`` spawns a fresh pane per transition, so an issue
accumulates one idle pane per completed phase. This test drives
INIT -> PLANNED -> RED -> GREEN and pins a single persistent pane plus
respawn-in-place, then asserts a BLOCKED phase triggers no respawn.
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

_CREATE_OPS = ("new_persona_surface", "new_surface", "new_workspace")


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
    def creation_count(self) -> int:
        return sum(1 for c in self.calls if c["op"] in _CREATE_OPS)

    def respawn_count(self) -> int:
        return sum(1 for c in self.calls if c["op"] == "respawn")

    def live_panes(self) -> list[str]:
        return [r for r, p in self.panes.items() if p["live"]]


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


def test_one_pane_across_lifecycle_blocked_intact(tmp_path, monkeypatch):
    """One pane spans INIT->PLANNED->RED->GREEN; a BLOCKED phase leaves it intact."""
    fake_mx = FakeCmuxMx()
    spawn_handler = _patch_spawn_env(tmp_path, monkeypatch, fake_mx)

    ctx = CoachContext(issue_number=730, multiplexer_mode="pane")

    lifecycle = [
        Transition(src=Phase.INIT, dst=Phase.PLANNED),
        Transition(src=Phase.PLANNED, dst=Phase.RED),
        Transition(src=Phase.RED, dst=Phase.GREEN),
    ]
    for transition in lifecycle:
        assert spawn_handler.handle(ctx, transition) == HandlerResult.HANDLED

    # The issue occupies exactly one pane (surface ATDD<N>) across all phases.
    live = fake_mx.live_panes()
    assert len(live) == 1, (
        f"expected exactly one pane for the issue across 3 phase transitions; "
        f"got {len(live)} (a new pane was spawned per phase)"
    )
    assert fake_mx.panes[live[0]]["name"] == "ATDD730", (
        f"the issue surface is not named ATDD730: {fake_mx.panes[live[0]]['name']!r}"
    )
    # Only the first phase creates a pane; the rest respawn in place.
    assert fake_mx.creation_count() == 1, (
        f"expected one pane creation; got {fake_mx.creation_count()}"
    )
    assert fake_mx.respawn_count() >= 2, (
        f"expected the 2 later transitions to respawn in place; "
        f"respawns={fake_mx.respawn_count()}"
    )

    # A BLOCKED phase triggers no respawn — the pane and agent are left intact.
    respawns_before_block = fake_mx.respawn_count()
    result = spawn_handler.handle(ctx, Transition(src=Phase.GREEN, dst=Phase.BLOCKED))
    assert result == HandlerResult.NOOP, (
        f"a BLOCKED transition must not spawn or respawn; got {result!r}"
    )
    assert fake_mx.respawn_count() == respawns_before_block, (
        "a BLOCKED phase respawned the persona — the pane must be left intact"
    )
    assert len(fake_mx.live_panes()) == 1, "the issue pane was disturbed by BLOCKED"
    assert fake_mx.panes[live[0]]["live"], "the BLOCKED issue's pane was closed"
