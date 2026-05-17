# URN: test:integration-hardening:coach-single-command-driver:L003-INTEGRATION-003-universal-cospawn-test-passes
# Acceptance: acc:integration-hardening:L003-INTEGRATION-001-spawn-cli-produces-persona-and-observer
# Acceptance: acc:integration-hardening:L003-INTEGRATION-002-coach-still-cospawns
# Acceptance: acc:integration-hardening:L003-INTEGRATION-003-universal-cospawn-test-passes
# WMBT: wmbt:integration-hardening:L003
# Phase: RED
# Layer: integration
"""L003-INTEGRATION-003 — substrate universality: every entry point calls new_persona_surface.

Table-driven enumeration of every entry point that creates a persona surface.
For each entry point: asserts it calls multiplexer.new_persona_surface (via
FakeMultiplexer injection) rather than bare new_surface for the persona.
This test is a ratchet — adding a new entry point that bypasses new_persona_surface
will cause it to fail here before it reaches CI.

Entry points enumerated (>= 3 required per L003-INTEGRATION-003):
1. cmd_spawn(multiplexer_mode='pane') — direct API, pane mode
2. cmd_spawn(multiplexer_mode='auto') — direct API, auto mode
3. handlers/spawn.handle(ctx, INIT->PLANNED) — coach state machine (pane mode)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atdd.coach.utils.multiplexer import FakeMultiplexer

pytestmark = [pytest.mark.platform]


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
    """Entry point 1: cmd_spawn with multiplexer_mode='pane'."""
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
    from atdd.coach.utils.session_naming import compute_repo_short_name
    monkeypatch.setattr(cfg_mod, "load_atdd_config", lambda p: {})
    monkeypatch.setattr(
        "atdd.coach.commands.spawn.compute_repo_short_name",
        lambda cfg: "atdd",
    )
    monkeypatch.setattr(
        "atdd.coach.commands.spawn._build_arch_section",
        lambda issue: None,
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
        multiplexer_mode="pane",
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
    """Entry point 3: handlers/spawn.handle() (coach state machine, pane mode)."""
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

    ctx = CoachContext(
        issue_number=999,
        llm="claude-code",
        multiplexer=fake_mx,
        multiplexer_mode="pane",
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
# Parametrized universality assertion
# ---------------------------------------------------------------------------


ENTRY_POINTS = [
    ("cmd_spawn_pane", _spawn_via_cmd_spawn_pane),
    ("cmd_spawn_auto", _spawn_via_cmd_spawn_auto),
    ("coach_handler_pane", _spawn_via_coach_handler),
]


@pytest.mark.parametrize("entry_point_name,invoke_fn", ENTRY_POINTS)
def test_entry_point_calls_new_persona_surface(
    entry_point_name, invoke_fn, tmp_path, monkeypatch
):
    """Every entry point must produce at least 1 new_persona_surface_calls entry."""
    fake_mx = invoke_fn(tmp_path, monkeypatch)

    assert len(fake_mx.new_persona_surface_calls) >= 1, (
        f"Entry point '{entry_point_name}' did not call new_persona_surface. "
        f"calls={fake_mx.calls}"
    )


@pytest.mark.parametrize("entry_point_name,invoke_fn", ENTRY_POINTS)
def test_entry_point_produces_observer_surface(
    entry_point_name, invoke_fn, tmp_path, monkeypatch
):
    """Every entry point must produce a surface with the observer link marker.

    Naming convention (#695): persona is `<canonical_name>`, observer is
    `<canonical_name>:obs` (sort-adjacent + ':obs' link suffix). Accept either
    the legacy 'observer' substring OR the new ':obs' suffix for backward compat.
    """
    fake_mx = invoke_fn(tmp_path, monkeypatch)

    surface_calls = [c for c in fake_mx.calls if c["op"] == "new_surface"]
    observer_calls = [
        c for c in surface_calls
        if "observer" in (c.get("name") or "").lower()
        or (c.get("name") or "").lower().endswith(":obs")
    ]
    assert len(observer_calls) >= 1, (
        f"Entry point '{entry_point_name}' did not produce an observer surface. "
        f"surface_calls={surface_calls}"
    )
