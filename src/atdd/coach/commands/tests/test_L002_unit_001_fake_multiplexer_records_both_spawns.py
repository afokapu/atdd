# URN: test:integration-hardening:coach-single-command-driver:L002-UNIT-001-fake-multiplexer-records-both-spawns
# Acceptance: acc:integration-hardening:L002-UNIT-001-fake-multiplexer-records-both-spawns
# WMBT: wmbt:integration-hardening:L002
# Phase: RED
# Layer: unit
"""L002-UNIT-001 — FakeMultiplexer records exactly 2 spawn calls at INIT→PLANNED.

handle(ctx, transition=INIT→PLANNED) must call the multiplexer twice:
once for the planner persona and once for the observer sidecar.
FakeMultiplexer isolates the test from any real cmux daemon (R1, #645).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]


class _FakeMx:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def new_workspace(self, cwd: str, command: str, name: Any = None) -> str:
        ref = f"workspace:{len(self.calls) + 1}"
        self.calls.append({"op": "new_workspace", "cwd": cwd, "command": command, "name": name, "ref": ref})
        return ref

    def new_surface(
        self,
        workspace_ref: Any = None,
        pane_ref: Any = None,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
        direction: Any = None,
    ) -> str:
        ref = f"surface:{len(self.calls) + 1}"
        self.calls.append({"op": "new_surface", "cwd": cwd, "command": command, "name": name, "ref": ref})
        return ref

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})

    def read_screen(self, ref: str, lines: int = 50) -> str:
        return ""

    def send(self, ref: str, text: str) -> None:
        pass

    def send_key(self, ref: str, key: str) -> None:
        pass

    def list_workspaces(self) -> list[str]:
        return []

    def close(self, ref: str) -> None:
        pass


def _make_ctx(tmp_path: Path, fake_mx: _FakeMx):
    from atdd.coach.handlers.state_machine import CoachContext

    return CoachContext(
        issue_number=650,
        llm="claude-code",
        multiplexer=fake_mx,
        multiplexer_mode="pane",
        dry_run=False,
        max_retries=0,
        escalation_channel=None,
        persona_llm={},
        coach_run_id=None,
        runtime_dir=str(tmp_path / ".atdd" / "runtime"),
    )


def test_both_spawns_recorded_by_fake_multiplexer(tmp_path, monkeypatch):
    """handle() at INIT→PLANNED records 2 spawn calls — persona + observer."""
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.handlers.state_machine import Phase, Transition
    from atdd.coach.commands import spawn as cmd_spawn_mod

    fake_mx = _FakeMx()
    wt = tmp_path / "wt"
    wt.mkdir()

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx)

    ctx = _make_ctx(tmp_path, fake_mx)
    transition = Transition(src=Phase.INIT, dst=Phase.PLANNED)

    result = spawn_handler.handle(ctx, transition)

    from atdd.coach.handlers.state_machine import HandlerResult
    assert result == HandlerResult.HANDLED, f"Expected HANDLED, got {result}"

    spawn_calls = [c for c in fake_mx.calls if c["op"] in ("new_surface", "new_workspace")]
    assert len(spawn_calls) == 2, (
        f"Expected exactly 2 spawn calls (persona + observer), got {len(spawn_calls)}: {spawn_calls}"
    )

    planner_calls = [c for c in spawn_calls if "planner" in (c.get("command") or "")]
    assert len(planner_calls) == 1, (
        f"Expected 1 planner spawn call, got {len(planner_calls)}: {spawn_calls}"
    )

    observer_calls = [c for c in spawn_calls if "observer" in (c.get("command") or "")]
    assert len(observer_calls) == 1, (
        f"Expected 1 observer spawn call, got {len(observer_calls)}: {spawn_calls}"
    )


def test_observer_surface_name_follows_pattern(tmp_path, monkeypatch):
    """Observer surface name must match ATDD<N>-observer-planned pattern."""
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.handlers.state_machine import Phase, Transition
    from atdd.coach.commands import spawn as cmd_spawn_mod

    fake_mx = _FakeMx()
    wt = tmp_path / "wt"
    wt.mkdir()

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx)

    ctx = _make_ctx(tmp_path, fake_mx)
    transition = Transition(src=Phase.INIT, dst=Phase.PLANNED)

    spawn_handler.handle(ctx, transition)

    spawn_calls = [c for c in fake_mx.calls if c["op"] in ("new_surface", "new_workspace")]
    observer_calls = [c for c in spawn_calls if "observer" in (c.get("command") or "")]
    assert observer_calls, f"No observer call found in: {spawn_calls}"

    observer_name = observer_calls[0].get("name") or ""
    assert "observer" in observer_name.lower(), (
        f"Observer surface name should contain 'observer', got: {observer_name!r}"
    )
    assert "planned" in observer_name.lower() or "650" in observer_name, (
        f"Observer surface name should reference phase or issue, got: {observer_name!r}"
    )
