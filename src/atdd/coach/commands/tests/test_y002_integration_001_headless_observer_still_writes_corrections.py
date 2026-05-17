# URN: test:consolidate-coach-workspace:headless-observer:Y002-INTEGRATION-001-headless-observer-still-writes-corrections
# Acceptance: acc:consolidate-coach-workspace:Y002-INTEGRATION-001-headless-observer-still-writes-corrections
# WMBT: wmbt:consolidate-coach-workspace:Y002
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""Y002-INTEGRATION-001 — the headless observer process is launched with the
agent runtime wiring it needs to keep appending ``corrections.jsonl``, and no
observer surface/tab is created.

RED: ``_spawn_observer`` creates an ``…:obs`` multiplexer surface and never
launches a background process. This test pins that the observer is started as
a detached ``atdd observer run`` subprocess pointed at the agent's runtime dir
(where ``agents/<id>/corrections.jsonl`` lives) — with no surface created.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.platform]


class FakeMx:
    """Multiplexer double — records every surface creation."""

    name = "fake"

    def __init__(self) -> None:
        self.created: list[Any] = []

    def new_surface(self, *a: Any, **k: Any) -> str:
        self.created.append(k.get("name"))
        return "surface:obs"

    def new_surface_in_pane(self, *a: Any, **k: Any) -> str:
        self.created.append(k.get("name"))
        return "surface:obs"

    def surface_to_pane(self, ref: Any) -> str:
        return "pane:1"


class _DummyProc:
    pid = 4242


def _argv_to_str(args: tuple, kwargs: dict) -> str:
    """Flatten a Popen call's command into a single inspectable string."""
    cmd = kwargs.get("args")
    if cmd is None and args:
        cmd = args[0]
    if isinstance(cmd, (list, tuple)):
        return " ".join(str(p) for p in cmd)
    return str(cmd)


def test_headless_observer_still_writes_corrections(monkeypatch):
    """The headless observer subprocess carries `--agent-id` and the agent
    runtime dir, and is co-located with no `:obs` surface."""
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import spawn as cmd_spawn_mod
    from atdd.coach.handlers.state_machine import CoachContext

    fake_mx = FakeMx()
    popen_calls: list[tuple] = []

    def _fake_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return _DummyProc()

    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer",
                        lambda preferred=None: fake_mx)
    monkeypatch.setattr(subprocess, "Popen", _fake_popen)

    ctx = CoachContext(issue_number=736, multiplexer_mode="workspace")
    runtime_root = Path("/tmp/atdd-rt-736")
    persona_agent_id = "tester-736-abc"

    spawn_handler._spawn_observer(
        ctx, "RED", Path("/tmp/wt-736"),
        persona_agent_id, runtime_root, persona_surface_ref=None,
    )

    # No observer UI surface anywhere.
    assert fake_mx.created == [], (
        f"headless observer must create no multiplexer surface; "
        f"created: {fake_mx.created}"
    )

    # Exactly one detached `atdd observer run` subprocess, wired to the
    # agent runtime dir so corrections.jsonl keeps being written.
    assert len(popen_calls) == 1, (
        f"expected one headless observer subprocess; got {len(popen_calls)}"
    )
    cmd = _argv_to_str(*popen_calls[0])
    assert "atdd observer run" in cmd, f"observer not launched via CLI: {cmd!r}"
    assert "--agent-id" in cmd, f"observer subprocess missing --agent-id: {cmd!r}"
    assert str(runtime_root) in cmd, (
        f"observer subprocess not pointed at the agent runtime dir "
        f"{str(runtime_root)!r} — corrections.jsonl would not be written: {cmd!r}"
    )
