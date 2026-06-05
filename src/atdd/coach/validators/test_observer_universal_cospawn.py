# URN: test:integration-hardening:coach-single-command-driver:L003-INTEGRATION-003-universal-cospawn-test-passes
# Acceptance: acc:integration-hardening:L003-INTEGRATION-001-spawn-cli-produces-persona-and-observer
# Acceptance: acc:integration-hardening:L003-INTEGRATION-002-coach-still-cospawns
# Acceptance: acc:integration-hardening:L003-INTEGRATION-003-universal-cospawn-test-passes
# WMBT: wmbt:integration-hardening:L003
# Phase: GREEN
# Layer: integration
"""L003-INTEGRATION-003 — substrate universality: every entry point creates
exactly one persona surface and NO per-worker ':obs' observer surface.

Issue #754 replaced per-worker observer spawning with a single
MultiAgentObserver started once by _execute_cold_start. This test is updated
to verify the new contract: spawn entry points create one persona surface
(via new_surface, not new_persona_surface) and zero observer surfaces.

Entry points enumerated (>= 3 required per L003-INTEGRATION-003):
1. cmd_spawn(multiplexer_mode='surface') — direct API, surface mode (canonical since #830)
2. cmd_spawn(multiplexer_mode='auto') — direct API, auto mode
3. handlers/spawn.handle(ctx, INIT->PLANNED) — coach state machine (surface mode)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atdd.coach.utils.multiplexer import FakeMultiplexer

pytestmark = [pytest.mark.platform]


@pytest.fixture(autouse=True)
def _legacy_spawn_transport(monkeypatch):
    """These entry-point tests assert the legacy tui-scrape surface/observer
    behaviour against a FakeMultiplexer (no real shim heartbeat). Since #978/E043
    the spawn DEFAULT is ``cmux-native`` and ``ATDD_USE_LEGACY_SPAWN=1`` routes to
    the **shim** (cli-return), so to reach the tui-scrape paste path these tests
    pin it explicitly via ``ATDD_CORRECTION_TRANSPORT=tui-scrape`` (an override
    wins by precedence). Scoped to this module so the delicate Y003 core.bare
    guard self-test elsewhere in this directory is untouched."""
    monkeypatch.delenv("ATDD_USE_LEGACY_SPAWN", raising=False)
    monkeypatch.setenv("ATDD_CORRECTION_TRANSPORT", "tui-scrape")
    yield


# ---------------------------------------------------------------------------
# Shared setup helpers
# ---------------------------------------------------------------------------


def _wt(tmp_path: Path) -> Path:
    wt = tmp_path / "wt"
    wt.mkdir(parents=True, exist_ok=True)
    return wt


def _runtime(tmp_path: Path) -> Path:
    rt = tmp_path / ".atdd" / "runtime"
    rt.mkdir(parents=True, exist_ok=True)
    return rt


# ---------------------------------------------------------------------------
# Entry-point invocations
# ---------------------------------------------------------------------------


def _spawn_via_cmd_spawn_pane(tmp_path: Path, monkeypatch) -> FakeMultiplexer:
    """Entry point 1: cmd_spawn with multiplexer_mode='surface' (canonical since #830)."""
    from atdd.coach.commands import spawn as cmd_spawn_mod, session_template

    wt = _wt(tmp_path)
    rt = _runtime(tmp_path)
    fake_mx = FakeMultiplexer()

    monkeypatch.setattr(
        session_template, "fetch_issue",
        lambda n: {"number": n, "title": "test", "body": ""},
    )
    monkeypatch.setattr(
        session_template, "render",
        lambda ctx: "# mock prompt",
    )

    from atdd.coach.utils import config as cfg_mod
    monkeypatch.setattr(cfg_mod, "load_atdd_config", lambda p: {})
    monkeypatch.setattr(
        "atdd.coach.commands.spawn.compute_repo_short_name",
        lambda cfg: "atdd",
    )
    monkeypatch.setattr(
        "atdd.coach.commands.spawn._build_arch_section",
        lambda issue: None,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.spawn._pre_trust_worktree",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.spawn.SurfaceMarkerProbe.wait_for_ready",
        lambda self, *a, **kw: None,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.spawn._assert_worker_processing",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.spawn._verify_stage",
        lambda *a, **kw: None,
    )

    cmd_spawn_mod.cmd_spawn(
        persona="planner",
        llm="claude-code",
        worktree=wt,
        issue=999,
        agent_id="test-agent-001",
        runtime_root=rt,
        phase="planned",
        multiplexer=fake_mx,
        multiplexer_mode="surface",
    )
    return fake_mx


def _spawn_via_cmd_spawn_auto(tmp_path: Path, monkeypatch) -> FakeMultiplexer:
    """Entry point 2: cmd_spawn with multiplexer_mode='auto'."""
    from atdd.coach.commands import spawn as cmd_spawn_mod, session_template

    wt = _wt(tmp_path)
    rt = _runtime(tmp_path)
    fake_mx = FakeMultiplexer()

    monkeypatch.setattr(
        session_template, "fetch_issue",
        lambda n: {"number": n, "title": "test", "body": ""},
    )
    monkeypatch.setattr(
        session_template, "render",
        lambda ctx: "# mock prompt",
    )
    from atdd.coach.utils import config as cfg_mod
    monkeypatch.setattr(cfg_mod, "load_atdd_config", lambda p: {})
    monkeypatch.setattr(
        "atdd.coach.commands.spawn.compute_repo_short_name",
        lambda cfg: "atdd",
    )
    monkeypatch.setattr(
        "atdd.coach.commands.spawn._build_arch_section",
        lambda issue: None,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.spawn._pre_trust_worktree",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.spawn.SurfaceMarkerProbe.wait_for_ready",
        lambda self, *a, **kw: None,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.spawn._assert_worker_processing",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.spawn._verify_stage",
        lambda *a, **kw: None,
    )

    cmd_spawn_mod.cmd_spawn(
        persona="tester",
        llm="claude-code",
        worktree=wt,
        issue=999,
        agent_id="test-agent-002",
        runtime_root=rt,
        phase="red",
        multiplexer=fake_mx,
        multiplexer_mode="auto",
    )
    return fake_mx


def _spawn_via_coach_handler(tmp_path: Path, monkeypatch) -> FakeMultiplexer:
    """Entry point 3: handlers/spawn.handle() (coach state machine, surface mode)."""
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.handlers.state_machine import CoachContext, Phase, Transition
    from atdd.coach.commands import spawn as cmd_spawn_mod

    wt = _wt(tmp_path)
    rt = _runtime(tmp_path)
    fake_mx = FakeMultiplexer()

    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", rt)
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake_mx)

    from atdd.coach.commands import session_template
    monkeypatch.setattr(
        session_template, "fetch_issue",
        lambda n: {"number": n, "title": "test", "body": ""},
    )
    monkeypatch.setattr(session_template, "render", lambda ctx: "# mock prompt")
    monkeypatch.setattr(
        "atdd.coach.commands.spawn.compute_repo_short_name",
        lambda cfg: "atdd",
    )
    monkeypatch.setattr(
        "atdd.coach.commands.spawn._build_arch_section",
        lambda issue: None,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.spawn._pre_trust_worktree",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.spawn.SurfaceMarkerProbe.wait_for_ready",
        lambda self, *a, **kw: None,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.spawn._verify_stage",
        lambda *a, **kw: None,
    )

    ctx = CoachContext(
        issue_number=999,
        llm="claude-code",
        multiplexer=fake_mx,
        multiplexer_mode="surface",
        dry_run=False,
        max_retries=0,
        escalation_channel=None,
        persona_llm={},
        coach_run_id=None,
        runtime_dir=str(rt),
    )

    spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))
    return fake_mx


# ---------------------------------------------------------------------------
# Parametrized universality assertions (updated for issue #754 contract)
# ---------------------------------------------------------------------------


ENTRY_POINTS = [
    ("cmd_spawn_surface", _spawn_via_cmd_spawn_pane),
    ("cmd_spawn_auto", _spawn_via_cmd_spawn_auto),
    ("coach_handler_surface", _spawn_via_coach_handler),
]


@pytest.mark.parametrize("entry_point_name,invoke_fn", ENTRY_POINTS)
def test_entry_point_creates_exactly_one_persona_surface(
    entry_point_name, invoke_fn, tmp_path, monkeypatch
):
    """Every entry point creates exactly one persona surface via new_surface_in_pane
    (canonical since #830 — cmux new-surface --pane <ref>), not new_persona_surface.

    Issue #754: per-worker observers removed. Entry points no longer call
    new_persona_surface — they call new_surface_in_pane for the worker only.
    """
    fake_mx = invoke_fn(tmp_path, monkeypatch)

    surface_calls = [
        c for c in fake_mx.calls
        if c["op"] in ("new_surface", "new_surface_in_pane")
    ]
    persona_surface_calls = [
        c for c in surface_calls
        if not (
            "observer" in (c.get("name") or "").lower()
            or (c.get("name") or "").lower().endswith(":obs")
        )
    ]
    assert len(persona_surface_calls) >= 1, (
        f"Entry point '{entry_point_name}' did not create a persona surface. "
        f"surface_calls={surface_calls}"
    )
    assert len(fake_mx.new_persona_surface_calls) == 0, (
        f"Entry point '{entry_point_name}' called new_persona_surface "
        f"(which co-spawns an observer) — issue #754 removed per-worker observers. "
        f"new_persona_surface_calls={fake_mx.new_persona_surface_calls}"
    )


@pytest.mark.parametrize("entry_point_name,invoke_fn", ENTRY_POINTS)
def test_entry_point_produces_no_observer_surface(
    entry_point_name, invoke_fn, tmp_path, monkeypatch
):
    """Every entry point must NOT produce a per-worker ':obs' observer surface.

    Issue #754: the single coach-level MultiAgentObserver is started by
    _execute_cold_start, not by per-worker spawn entry points.
    """
    fake_mx = invoke_fn(tmp_path, monkeypatch)

    surface_calls = [
        c for c in fake_mx.calls
        if c["op"] in ("new_surface", "new_surface_in_pane")
    ]
    observer_calls = [
        c for c in surface_calls
        if "observer" in (c.get("name") or "").lower()
        or (c.get("name") or "").lower().endswith(":obs")
    ]
    assert len(observer_calls) == 0, (
        f"Entry point '{entry_point_name}' produced per-worker observer surface(s): "
        f"{observer_calls}. Issue #754: observer is coach-level, not per-worker."
    )
