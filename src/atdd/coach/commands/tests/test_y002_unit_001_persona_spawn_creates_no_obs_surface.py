# URN: test:consolidate-coach-workspace:headless-observer:Y002-UNIT-001-persona-spawn-creates-no-obs-surface
# Acceptance: acc:consolidate-coach-workspace:Y002-UNIT-001-persona-spawn-creates-no-obs-surface
# WMBT: wmbt:consolidate-coach-workspace:Y002
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""Y002-UNIT-001 — spawning a persona's observer creates no multiplexer
surface; the observer runs as a detached background subprocess.

RED: ``_spawn_observer`` co-spawns the observer as a visible ``…:obs`` surface
(``new_surface`` / ``new_surface_in_pane``), so every worker is two tabs. This
test pins the headless contract — ``_spawn_observer`` launches the observer via
``subprocess.Popen`` and creates zero multiplexer surfaces.
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


def test_persona_spawn_creates_no_obs_surface(monkeypatch):
    """`_spawn_observer` launches a background subprocess and creates no
    `:obs` multiplexer surface."""
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

    ctx = CoachContext(issue_number=736, multiplexer_mode="pane")

    spawn_handler._spawn_observer(
        ctx, "RED", Path("/tmp/wt-736"),
        "tester-736-abc", Path("/tmp/rt"), persona_surface_ref="pane:1",
    )

    obs_surfaces = [n for n in fake_mx.created if isinstance(n, str) and n.endswith(":obs")]
    assert obs_surfaces == [], (
        f"observer co-spawned as visible surface(s) {obs_surfaces} — the "
        f"observer must run headless with no UI surface"
    )
    assert fake_mx.created == [], (
        f"observer launch created multiplexer surface(s) {fake_mx.created}; "
        f"a headless observer creates none"
    )
    assert len(popen_calls) == 1, (
        f"observer was not started as a detached background subprocess "
        f"(subprocess.Popen calls: {len(popen_calls)})"
    )
