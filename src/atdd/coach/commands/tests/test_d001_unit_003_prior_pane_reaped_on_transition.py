# URN: test:coach-wave-orchestration:within-wave-concurrency-and-pane-identity:D001-UNIT-003-prior-pane-reaped-on-transition
# Acceptance: acc:coach-wave-orchestration:D001-UNIT-003-prior-pane-reaped-on-transition
# WMBT: wmbt:coach-wave-orchestration:D001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""D001-UNIT-003 — on a phase transition the spawn handler reaps (closes) or
marks-inactive the prior phase's persona pane.

RED: ``handlers/spawn.py`` creates a fresh persona pane per transition but never
closes the previous one, so coach accumulates one identically-named idle pane
per completed phase. This test pins exactly-one reap of the prior pane.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pytest

from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Phase, Transition

pytestmark = [pytest.mark.platform]


SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-within-wave-serial-execution` |
| Train | `none` |
| Feature | persona pane identity |
"""


class FakePaneMx:
    """Pane-mode multiplexer double tracking live panes + reap calls."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.panes: dict[str, dict] = {}        # ref -> {"name", "live"}
        self.persona_panes: list[str] = []      # persona-pane refs, creation order
        self._n = 0

    def _add_persona(self, name: Any) -> str:
        self._n += 1
        ref = f"pane:{self._n}"
        self.panes[ref] = {"name": name, "live": True}
        self.persona_panes.append(ref)
        return ref

    def new_persona_surface(
        self, cwd: Any = None, command: Any = None, name: Any = None,
        *, observer_runtime_root: str = "", observer_agent_id: str = "",
        observer_name: str = "", observer_command: str = "", **_: Any,
    ) -> str:
        ref = self._add_persona(name)
        self.calls.append({"op": "new_persona_surface", "name": name, "ref": ref})
        return ref

    def new_surface(self, workspace_ref: Any = None, pane_ref: Any = None,
                    cwd: Any = None, command: Any = None, name: Any = None,
                    direction: Any = None) -> str:
        ref = self._add_persona(name)
        self.calls.append({"op": "new_surface", "name": name, "ref": ref})
        return ref

    def new_workspace(self, cwd: Any = None, command: Any = None,
                      name: Optional[str] = None) -> str:
        ref = self._add_persona(name)
        self.calls.append({"op": "new_workspace", "name": name, "ref": ref})
        return ref

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})
        if ref in self.panes:
            self.panes[ref]["name"] = name

    def close(self, ref: str) -> None:
        self.calls.append({"op": "close", "ref": ref})
        if ref in self.panes:
            self.panes[ref]["live"] = False

    def mark_inactive(self, ref: str) -> None:
        self.calls.append({"op": "mark_inactive", "ref": ref})
        if ref in self.panes:
            self.panes[ref]["live"] = False

    def set_inactive(self, ref: str) -> None:
        self.mark_inactive(ref)

    def send(self, ref: str, text: str) -> None:
        self.calls.append({"op": "send", "ref": ref, "text": text})

    def send_key(self, ref: str, key: str) -> None:
        self.calls.append({"op": "send_key", "ref": ref, "key": key})

    def paste_text(self, ref: str, text: str) -> None:
        self.calls.append({"op": "paste_text", "ref": ref})

    def read_screen(self, ref: str, lines: int = 50) -> str:
        return ""

    def list_workspaces(self) -> list[str]:
        return [p["name"] for p in self.panes.values() if p["live"]]

    def list_panes(self) -> list[dict]:
        return [
            {"ref": ref, "name": p["name"]}
            for ref, p in self.panes.items() if p["live"]
        ]

    # --- test introspection ------------------------------------------------
    def live_persona_panes(self) -> list[str]:
        return [r for r in self.persona_panes if self.panes[r]["live"]]

    def reap_count(self, ref: str) -> int:
        return sum(
            1 for c in self.calls
            if c["op"] in ("close", "mark_inactive") and c.get("ref") == ref
        )


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
        lambda n: {"number": n, "title": "persona pane identity", "body": SAMPLE_BODY},
    )
    return spawn_handler


def test_prior_persona_pane_reaped_on_transition(tmp_path, monkeypatch):
    """The planner pane is reaped exactly once when the tester pane is spawned."""
    fake_mx = FakePaneMx()
    spawn_handler = _patch_spawn_env(tmp_path, monkeypatch, fake_mx)

    # One CoachContext drives the issue across transitions, as in _drive_single_issue.
    ctx = CoachContext(issue_number=730, multiplexer_mode="pane")

    # Prior phase: planner persona pane spawned at INIT -> PLANNED.
    r1 = spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))
    assert r1 == HandlerResult.HANDLED
    live_after_planner = fake_mx.live_persona_panes()
    assert len(live_after_planner) == 1, f"expected 1 planner pane, got {live_after_planner}"
    planner_ref = live_after_planner[0]
    reaps_before = fake_mx.reap_count(planner_ref)

    # Next phase: tester persona pane spawned at PLANNED -> RED.
    r2 = spawn_handler.handle(ctx, Transition(src=Phase.PLANNED, dst=Phase.RED))
    assert r2 == HandlerResult.HANDLED

    # The prior planner pane received exactly one reap (close / mark-inactive).
    reaps_after = fake_mx.reap_count(planner_ref)
    assert reaps_after - reaps_before == 1, (
        f"prior planner pane {planner_ref} expected exactly 1 reap on the "
        f"phase transition; got {reaps_after - reaps_before}"
    )
    # No pane carrying the prior phase's name is left in an active state.
    assert not fake_mx.panes[planner_ref]["live"], (
        "the planner pane is still live after the RED-phase spawn"
    )
