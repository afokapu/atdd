# URN: test:spawn-agents:smoke-persona-spawn-integrity:E005-INTEGRATION-002-coach-blocks-loudly-on-persona-failure
# Acceptance: acc:spawn-agents:E005-INTEGRATION-002-coach-blocks-loudly-on-persona-failure
# WMBT: wmbt:spawn-agents:E005
# Phase: RED
# Layer: integration
"""E005-INTEGRATION-002 — when every persona-spawn attempt fails to
materialise, the coach BLOCKs and escalates instead of staying in SMOKE.

Driving the coach spawn handler for a GREEN→SMOKE transition against a
multiplexer in which every persona-spawn attempt fails MUST yield
``HandlerResult.ERROR`` (which the coach state machine maps to BLOCKED — the
issue does not remain in SMOKE), emit exactly one escalation message, and
leave no orphan ``tester-<issue>-<suffix>-observer/`` dir.

RED: today a persona spawn that produces no surface still returns a truthy
``cmd_spawn`` dict, so ``handle()`` returns ``HANDLED`` and the coach sits in
SMOKE forever. This test fails until the persona-materialisation gate (#733)
lands.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

from atdd.coach.handlers.state_machine import (
    CoachContext,
    HandlerResult,
    Phase,
    Transition,
)

pytestmark = [pytest.mark.platform]

SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-smoke-spawn-creates-observer-without-persona` |
| Train | `0002-coach-drives-lifecycle` |
"""


class _FakeMultiplexer:
    """A multiplexer in which every persona-spawn attempt fails to produce a
    persona surface (#733)."""

    name = "fake"

    def __init__(self, *, persona_materialises: bool = False) -> None:
        self.persona_materialises = persona_materialises
        self.calls: list[dict] = []
        self._surface_pane: dict[str, str] = {}

    def _record(self, op: str, **kw: Any) -> str:
        ref = f"surface:{len(self.calls) + 1}"
        self.calls.append({"op": op, "ref": ref, **kw})
        return ref

    def new_workspace(self, cwd: Any = None, command: Any = None, name: Any = None) -> str:
        return self._record("new_workspace", cwd=cwd, command=command, name=name)

    def new_surface(
        self,
        workspace_ref: Any = None,
        pane_ref: Any = None,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
        direction: Any = None,
    ) -> str:
        ref = self._record("new_surface", cwd=cwd, command=command, name=name)
        self._surface_pane[ref] = pane_ref or f"pane:{len(self.calls)}"
        return ref

    def new_surface_in_pane(
        self,
        pane_ref: str,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
    ) -> str:
        ref = self._record(
            "new_surface_in_pane", cwd=cwd, command=command, name=name, pane_ref=pane_ref
        )
        self._surface_pane[ref] = pane_ref
        return ref

    def surface_to_pane(self, surface_ref: str) -> str:
        return self._surface_pane.get(surface_ref, "pane:1")

    def new_persona_surface(
        self,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
        *,
        observer_runtime_root: str = "",
        observer_agent_id: str = "",
        observer_name: str = "",
        observer_command: str = "",
        **_: Any,
    ) -> Optional[str]:
        if not self.persona_materialises:
            return None
        return self.new_surface(cwd=cwd, command=command, name=name)

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})

    def send(self, ref: str, text: str) -> None:
        pass

    def send_key(self, ref: str, key: str) -> None:
        pass

    def read_screen(self, ref: str, lines: int = 50) -> str:
        return ""

    def list_workspaces(self) -> list[str]:
        return []

    def close(self, ref: str) -> None:
        pass


def test_coach_blocks_and_escalates_when_every_persona_spawn_fails(
    tmp_path, monkeypatch
):
    """A GREEN→SMOKE transition whose persona spawn never materialises yields
    ERROR + one escalation + no orphan observer dir."""
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import session_template
    from atdd.coach.commands import spawn as cmd_spawn_mod

    runtime_root = tmp_path / ".atdd" / "runtime"
    worktree = tmp_path / "wt"
    worktree.mkdir(parents=True)
    fake = _FakeMultiplexer(persona_materialises=False)

    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "smoke persona spawn", "body": SAMPLE_BODY},
    )
    monkeypatch.setattr(cmd_spawn_mod, "capture_session_uuid", lambda **kw: None)
    monkeypatch.setattr(
        cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake
    )
    monkeypatch.setattr(
        spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt"
    )
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: worktree)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(spawn_handler.time, "sleep", lambda s: None)

    escalations: list[str] = []
    monkeypatch.setattr(
        spawn_handler, "_escalate", lambda ctx, reason: escalations.append(reason)
    )

    ctx = CoachContext(
        issue_number=733,
        escalation_channel="file:./escalations.log",
        multiplexer_mode="pane",
    )
    result = spawn_handler.handle(
        ctx, Transition(src=Phase.GREEN, dst=Phase.SMOKE)
    )

    assert result == HandlerResult.ERROR, (
        f"a persona spawn that never materialises must yield ERROR (mapped to "
        f"BLOCKED), not {result} — the issue must not remain in SMOKE (#733)"
    )
    assert len(escalations) == 1, (
        f"exactly one escalation must be emitted on persona-spawn exhaustion, "
        f"got {escalations}"
    )

    agents_dir = runtime_root / "agents"
    if agents_dir.is_dir():
        orphans = [
            d for d in agents_dir.iterdir() if d.is_dir() and d.name.endswith("-observer")
        ]
        assert not orphans, (
            f"orphan observer dir(s) left behind after a failed persona spawn: "
            f"{[d.name for d in orphans]}"
        )
