# URN: test:integration-hardening:coach-single-command-driver:L002-INTEGRATION-002-observer-failure-does-not-block-persona
# Acceptance: acc:integration-hardening:L002-INTEGRATION-002-observer-failure-does-not-block-persona
# WMBT: wmbt:integration-hardening:L002
# Phase: RED
# Layer: integration
"""L002-INTEGRATION-002 — observer spawn failure does not block persona; HANDLED returned.

Observer failure is now caught inside Multiplexer.new_persona_surface (the substrate
primitive). A structured JSON event is emitted to stderr; the persona spawn still
succeeds and handle() returns HANDLED. _spawn_observer no longer exists in
handlers/spawn.py — this test validates the new primitive-level failure handling.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.platform]


class _FakeMxFailingObserver:
    """Fake multiplexer where new_persona_surface succeeds for persona but logs
    a structured failure event for the observer (simulating the primitive behavior
    when the observer co-spawn raises)."""

    name = "fake-failing-observer"

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
    ) -> str:
        persona_ref = self.new_surface(cwd=cwd, command=command, name=name)
        exc = RuntimeError("observer unavailable")
        print(
            json.dumps({
                "event": "observer_cospawn_failed",
                "persona_name": name,
                "observer_name": observer_name,
                "observer_agent_id": observer_agent_id,
                "error": str(exc),
            }),
            file=sys.stderr,
        )
        return persona_ref

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


def test_observer_failure_does_not_block_persona(tmp_path, monkeypatch, capsys):
    """new_persona_surface catches observer failure; handle() still returns HANDLED."""
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.handlers.state_machine import (
        CoachContext, HandlerResult, Phase, Transition,
    )
    from atdd.coach.commands import spawn as cmd_spawn_mod

    fake_mx = _FakeMxFailingObserver()
    wt = tmp_path / "wt"
    wt.mkdir()

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx)

    ctx = CoachContext(
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
    transition = Transition(src=Phase.INIT, dst=Phase.PLANNED)

    result = spawn_handler.handle(ctx, transition)

    assert result == HandlerResult.HANDLED, (
        f"Expected HANDLED even when observer fails, got {result}"
    )

    captured = capsys.readouterr()
    assert "observer" in captured.err.lower(), (
        f"Expected observer failure event in stderr, got: {captured.err!r}"
    )

    spawn_calls = [c for c in fake_mx.calls if c["op"] in ("new_surface", "new_workspace")]
    assert len(spawn_calls) >= 1, (
        f"Persona spawn must succeed even if observer fails; calls={fake_mx.calls}"
    )
