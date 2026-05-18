# URN: test:integration-hardening:coach-single-command-driver:L003-INTEGRATION-003-universal-cospawn-test-passes
# Acceptance: acc:integration-hardening:L003-INTEGRATION-001-spawn-cli-produces-persona-and-observer
# Acceptance: acc:integration-hardening:L003-INTEGRATION-002-coach-still-cospawns
# Acceptance: acc:integration-hardening:L003-INTEGRATION-003-universal-cospawn-test-passes
# WMBT: wmbt:integration-hardening:L003
# Phase: RED
# Layer: integration
"""L003-INTEGRATION-003 — substrate universality: every entry point launches the observer.

Table-driven enumeration of every entry point that creates a persona surface.
For each entry point: asserts it launches the per-worker observer — and that
the persona itself is exactly one surface, with no co-spawned ``:obs`` tab.

Issue #745 update: the observer no longer co-spawns as a visible ``:obs``
multiplexer surface via ``new_persona_surface``. It runs HEADLESS — a detached
``subprocess.Popen`` (``atdd observer run``), exactly as
``handlers/spawn.py::_spawn_observer`` already does (#736). This ratchet now
pins that headless contract: a new entry point that skips the observer, or
that resurrects the ``:obs`` surface, fails here before it reaches CI.

Entry points enumerated (>= 3 required per L003-INTEGRATION-003):
1. cmd_spawn(multiplexer_mode='pane') — direct API, pane mode
2. cmd_spawn(multiplexer_mode='auto') — direct API, auto mode
3. handlers/spawn.handle(ctx, INIT->PLANNED) — coach state machine (pane mode)
"""
from __future__ import annotations

import subprocess
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


class _DummyProc:
    pid = 4242

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def communicate(self, *a, **k):
        return ("", "")

    def wait(self, *a, **k):
        return 0


def _spy_popen(monkeypatch) -> list:
    """Patch subprocess.Popen to record detached launches; return the record."""
    popen_calls: list = []

    def _fake(cmd: Any, *a: Any, **k: Any):
        popen_calls.append(cmd)
        return _DummyProc()

    monkeypatch.setattr(subprocess, "Popen", _fake)
    return popen_calls


# ---------------------------------------------------------------------------
# Entry-point invocations — each returns (FakeMultiplexer, popen_calls)
# ---------------------------------------------------------------------------


def _spawn_via_cmd_spawn_pane(tmp_path: Path, monkeypatch) -> tuple[FakeMultiplexer, list]:
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
    monkeypatch.setattr(cfg_mod, "load_atdd_config", lambda p: {})
    monkeypatch.setattr(
        "atdd.coach.commands.spawn.compute_repo_short_name",
        lambda cfg: "atdd",
    )
    monkeypatch.setattr(
        "atdd.coach.commands.spawn._build_arch_section",
        lambda issue: None,
    )
    popen_calls = _spy_popen(monkeypatch)

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
    return fake_mx, popen_calls


def _spawn_via_cmd_spawn_auto(tmp_path: Path, monkeypatch) -> tuple[FakeMultiplexer, list]:
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
    popen_calls = _spy_popen(monkeypatch)

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
    return fake_mx, popen_calls


def _spawn_via_coach_handler(tmp_path: Path, monkeypatch) -> tuple[FakeMultiplexer, list]:
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

    # cmd_spawn (called inside handle) renders the launch prompt — stub the
    # issue fetch/render so it never shells out to `gh` via subprocess.
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
    popen_calls = _spy_popen(monkeypatch)

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
    return fake_mx, popen_calls


# ---------------------------------------------------------------------------
# Parametrized universality assertion
# ---------------------------------------------------------------------------


ENTRY_POINTS = [
    ("cmd_spawn_pane", _spawn_via_cmd_spawn_pane),
    ("cmd_spawn_auto", _spawn_via_cmd_spawn_auto),
    ("coach_handler_pane", _spawn_via_coach_handler),
]


def _observer_launches(popen_calls: list) -> list:
    """Detached subprocess launches whose argv invokes the observer."""
    launches = []
    for cmd in popen_calls:
        if isinstance(cmd, (list, tuple)) and "observer" in [str(x) for x in cmd]:
            launches.append(cmd)
        elif isinstance(cmd, str) and "observer" in cmd:
            launches.append(cmd)
    return launches


@pytest.mark.parametrize("entry_point_name,invoke_fn", ENTRY_POINTS)
def test_entry_point_launches_headless_observer(
    entry_point_name, invoke_fn, tmp_path, monkeypatch
):
    """Every entry point launches the observer as a detached subprocess."""
    _fake_mx, popen_calls = invoke_fn(tmp_path, monkeypatch)

    launches = _observer_launches(popen_calls)
    assert len(launches) >= 1, (
        f"Entry point '{entry_point_name}' did not launch the observer as a "
        f"detached subprocess. The observer must run headless via "
        f"subprocess.Popen (`atdd observer run`). popen_calls={popen_calls}"
    )


@pytest.mark.parametrize("entry_point_name,invoke_fn", ENTRY_POINTS)
def test_entry_point_creates_no_obs_surface(
    entry_point_name, invoke_fn, tmp_path, monkeypatch
):
    """Every entry point creates the persona surface only — no co-spawned
    ``:obs`` surface (the observer is headless, #745)."""
    fake_mx, _popen_calls = invoke_fn(tmp_path, monkeypatch)

    surface_calls = [c for c in fake_mx.calls if c["op"] == "new_surface"]
    obs_calls = [
        c for c in surface_calls
        if "observer" in (c.get("name") or "").lower()
        or (c.get("name") or "").lower().endswith(":obs")
    ]
    assert obs_calls == [], (
        f"Entry point '{entry_point_name}' co-spawned an observer `:obs` "
        f"surface — the observer must run headless with no UI surface. "
        f"surface_calls={surface_calls}"
    )
