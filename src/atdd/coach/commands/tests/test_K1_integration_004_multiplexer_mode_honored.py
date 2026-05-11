# URN: test:integration-hardening:coach-spawn-wiring:K001-INTEGRATION-004-multiplexer-mode-honored
# Acceptance: acc:integration-hardening:K001-INTEGRATION-004-multiplexer-mode-honored
# WMBT: wmbt:integration-hardening:K001
# Phase: RED
# Layer: integration
"""K001-INTEGRATION-004 — --multiplexer-mode dispatches to new_surface (pane) vs
new_workspace (workspace).

Verifies that when CoachContext.multiplexer_mode is "pane", the spawn call uses
new_surface on the multiplexer backend. When it is "workspace", new_workspace is used.
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
| Branch | `feat/coach-v9-k1-spawn-wiring-585` |
| Train | `0004-integration-hardening` |
| Feature | coach spawn wiring |
"""


class _TrackingMultiplexer:
    """Records every surface/workspace creation call."""

    name = "tracking"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def new_workspace(self, cwd: str, command: str, name: Any = None) -> str:
        ref = f"workspace:{len(self.calls) + 1}"
        self.calls.append({"op": "new_workspace", "ref": ref})
        return ref

    def new_surface(self, workspace_ref: Any = None, pane_ref: Any = None,
                    cwd: Any = None, command: Any = None,
                    name: Any = None, direction: Any = None) -> str:
        ref = f"surface:{len(self.calls) + 1}"
        self.calls.append({"op": "new_surface", "ref": ref})
        return ref

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})


def _setup_integration(tmp_path, monkeypatch, multiplexer_mode: str):
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import session_template, spawn as cmd_spawn_mod

    monkeypatch.setattr(
        session_template, "fetch_issue",
        lambda n: {"number": n, "title": "spawn wiring", "body": SAMPLE_BODY},
    )
    fake_mx = _TrackingMultiplexer()
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx)

    wt = tmp_path / "feat-coach-v9-k1-spawn-wiring-585"
    wt.mkdir(parents=True)
    runtime_root = tmp_path / ".atdd" / "runtime"

    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(
        spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt"
    )

    ctx = CoachContext(issue_number=585, multiplexer_mode=multiplexer_mode)
    return ctx, fake_mx


def test_pane_mode_calls_new_surface(tmp_path, monkeypatch):
    """multiplexer_mode='pane' must result in new_surface being called."""
    ctx, fake_mx = _setup_integration(tmp_path, monkeypatch, multiplexer_mode="pane")
    from atdd.coach.handlers import spawn as spawn_handler

    result = spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))

    assert result == HandlerResult.HANDLED
    surface_ops = [c["op"] for c in fake_mx.calls if c["op"] in ("new_surface", "new_workspace")]
    assert "new_surface" in surface_ops, (
        f"pane mode must call new_surface; got ops={surface_ops}"
    )
    assert "new_workspace" not in surface_ops, (
        f"pane mode must NOT call new_workspace; got ops={surface_ops}"
    )


def test_workspace_mode_calls_new_workspace(tmp_path, monkeypatch):
    """multiplexer_mode='workspace' must result in new_workspace being called."""
    ctx, fake_mx = _setup_integration(tmp_path, monkeypatch, multiplexer_mode="workspace")
    from atdd.coach.handlers import spawn as spawn_handler

    result = spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))

    assert result == HandlerResult.HANDLED
    surface_ops = [c["op"] for c in fake_mx.calls if c["op"] in ("new_surface", "new_workspace")]
    assert "new_workspace" in surface_ops, (
        f"workspace mode must call new_workspace; got ops={surface_ops}"
    )
    assert "new_surface" not in surface_ops, (
        f"workspace mode must NOT call new_surface; got ops={surface_ops}"
    )
