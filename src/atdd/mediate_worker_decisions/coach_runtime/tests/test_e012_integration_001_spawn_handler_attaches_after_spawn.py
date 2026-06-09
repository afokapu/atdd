# URN: test:mediate-worker-decisions:coach-runtime:E012-INTEGRATION-001-spawn-handler-attaches-after-spawn
# Acceptance: acc:mediate-worker-decisions:E012-INTEGRATION-001-spawn-handler-attaches-after-spawn
# WMBT: wmbt:mediate-worker-decisions:E012
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E012-INTEGRATION-001 — the spawn handler attaches a daemon after a spawn.

Driving the coach spawn handler through a successful worker spawn invokes the
dispatch->daemon attach with the freshly-spawned worker's surface ref, so the
dispatch flow leaves a mediating daemon attached. A spawn that yields no surface
ref does not attach.
"""
from __future__ import annotations

from typing import List, Optional

import pytest

from atdd.coach.handlers import spawn as spawn_handler
from atdd.coach.handlers.state_machine import (
    CoachContext,
    HandlerResult,
    Phase,
    Transition,
)


def _patch_spawn(monkeypatch, tmp_path, *, surface_ref: Optional[str]):
    worktree = tmp_path / "wt"
    worktree.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "prompt")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: worktree)
    monkeypatch.setattr(spawn_handler, "_resolve_llm", lambda *a, **k: "claude-code")
    monkeypatch.setattr(
        spawn_handler, "_spawn_with_retries",
        lambda *a, **k: ({"surface_ref": surface_ref} if surface_ref else {}),
    )
    monkeypatch.setattr(spawn_handler, "_persona_materialised", lambda *a, **k: True)


def test_handler_attaches_with_spawned_surface(tmp_path, monkeypatch):
    captured: List[str] = []
    monkeypatch.setattr(
        spawn_handler, "_attach_worker_daemon",
        lambda backend, surface_ref, **kw: captured.append(surface_ref),
        raising=False,
    )
    _patch_spawn(monkeypatch, tmp_path, surface_ref="surface:9")

    ctx = CoachContext(issue_number=1025, multiplexer_mode="surface")
    result = spawn_handler.handle(ctx, Transition(src=Phase.GREEN, dst=Phase.SMOKE))

    assert result == HandlerResult.HANDLED
    assert captured == ["surface:9"]  # attach invoked with the spawned worker surface


def test_handler_skips_attach_when_no_surface(tmp_path, monkeypatch):
    captured: List[str] = []
    monkeypatch.setattr(
        spawn_handler, "_attach_worker_daemon",
        lambda backend, surface_ref, **kw: captured.append(surface_ref),
        raising=False,
    )
    _patch_spawn(monkeypatch, tmp_path, surface_ref=None)

    ctx = CoachContext(issue_number=1025, multiplexer_mode="surface")
    spawn_handler.handle(ctx, Transition(src=Phase.GREEN, dst=Phase.SMOKE))

    assert captured == []  # no surface ref -> no attach
