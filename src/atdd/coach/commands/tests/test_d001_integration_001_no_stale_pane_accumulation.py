# URN: test:coach-wave-orchestration:within-wave-concurrency-and-pane-identity:D001-INTEGRATION-001-no-stale-pane-accumulation
# Acceptance: acc:coach-wave-orchestration:D001-INTEGRATION-001-no-stale-pane-accumulation
# WMBT: wmbt:coach-wave-orchestration:D001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""D001-INTEGRATION-001 — driving one issue across two phase transitions yields
distinctly-named persona panes and at most one live pane per issue.

RED: every per-phase persona pane is named identically ``ATDD<N>-<slug>`` and
the prior pane is never reaped, so coach accumulates identically-named idle
panes. This test drives INIT -> PLANNED -> RED through the spawn handler and
pins distinct names + a single live pane.
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
| Feature | persona pane identity |
"""


class FakePaneMx:
    """Pane-mode multiplexer double tracking live panes by name."""

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

    def live_persona_panes(self) -> list[str]:
        return [r for r in self.persona_panes if self.panes[r]["live"]]


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


def test_no_stale_pane_accumulation_across_transitions(tmp_path, monkeypatch):
    """INIT->PLANNED->RED yields distinct pane names and one live pane."""
    fake_mx = FakePaneMx()
    spawn_handler = _patch_spawn_env(tmp_path, monkeypatch, fake_mx)

    ctx = CoachContext(issue_number=730, multiplexer_mode="pane")

    r1 = spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))
    assert r1 == HandlerResult.HANDLED
    assert len(fake_mx.persona_panes) == 1, "planner phase spawned no persona pane"
    planner_ref = fake_mx.persona_panes[0]

    r2 = spawn_handler.handle(ctx, Transition(src=Phase.PLANNED, dst=Phase.RED))
    assert r2 == HandlerResult.HANDLED
    assert len(fake_mx.persona_panes) == 2, "tester phase spawned no persona pane"
    tester_ref = fake_mx.persona_panes[1]

    planner_name = fake_mx.panes[planner_ref]["name"]
    tester_name = fake_mx.panes[tester_ref]["name"]

    # The planner pane name and the tester pane name are distinct,
    # persona/phase-qualified strings.
    assert planner_name != tester_name, (
        f"planner and tester panes share an identical name: {planner_name!r}"
    )
    assert "planner" in planner_name, f"planner name not qualified: {planner_name!r}"
    assert "tester" in tester_name, f"tester name not qualified: {tester_name!r}"

    # After the RED-phase spawn, exactly one pane for the issue is live —
    # the prior planner pane was reaped or marked inactive.
    live = fake_mx.live_persona_panes()
    assert live == [tester_ref], (
        f"expected only the tester pane live; got {live} "
        f"(prior planner pane not reaped)"
    )

    # No two live panes for the issue share an identical name.
    live_names = [fake_mx.panes[r]["name"] for r in live]
    assert len(live_names) == len(set(live_names)), (
        f"two live panes share an identical name: {live_names}"
    )
