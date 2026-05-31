# URN: test:review-phase-boundaries:phase-boundary-review:E004-UNIT-001-routing-test-is-hermetic-no-multiplexer-spawn
# Acceptance: acc:review-phase-boundaries:E004-UNIT-001-routing-test-is-hermetic-no-multiplexer-spawn
# WMBT: wmbt:review-phase-boundaries:E004
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: test_existing_coach_number_invocation_not_broken exercises bare-issue-number → coach CLI routing without spawning a real cmux workspace or observer
"""RED Test for test:review-phase-boundaries:phase-boundary-review:E004-UNIT-001-routing-test-is-hermetic-no-multiplexer-spawn
wagon: review-phase-boundaries | feature: phase-boundary-review | phase: RED
WMBT: wmbt:review-phase-boundaries:E004

Purpose
-------
`test_existing_coach_number_invocation_not_broken` (in
test_e002_integration_001_cli_dispatch_routes_review.py) verifies that a bare
issue number still routes to the coach state machine after the `review`
subcommand was added. Its *intent* is narrow — CLI dispatch — but it currently
invokes the real coach via ``coach.run_cli(["358"])`` with no ``--dry-run`` and
no injected stub multiplexer. Finding cmux on the environment the real coach
spawns an ``ATDD358`` cmux workspace plus an observer and never tears them down.

This test runs that exact routing test under a SPY multiplexer (so it can
never touch real cmux) and asserts the routing test creates zero workspaces /
surfaces. It is RED-first:

* Before the hermeticity fix the routing test calls ``run_cli(["358"])`` — the
  cold-start path reaches the spawn handler, which resolves the (spied)
  multiplexer and records a workspace-create call → this test FAILS.
* After the fix the routing test calls ``run_cli(["358", "--dry-run"])`` — the
  spawn handler short-circuits at ``if ctx.dry_run`` before any multiplexer is
  resolved → the spy records nothing → this test PASSES.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.platform]


class _SpyMultiplexer:
    """Records every spawn / workspace-create call instead of touching cmux.

    Injected in place of the real backend so this test can never leak a real
    workspace, regardless of whether the routing test under inspection is
    hermetic yet.
    """

    name = "spy"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def new_workspace(self, cwd: str, command: str, name: Any = None) -> str:
        ref = f"workspace:{len(self.calls) + 1}"
        self.calls.append({"op": "new_workspace", "cwd": cwd, "command": command, "name": name, "ref": ref})
        return ref

    def new_surface(self, workspace_ref: Any = None, pane_ref: Any = None,
                    cwd: Any = None, command: Any = None,
                    name: Any = None, direction: Any = None) -> str:
        ref = f"surface:{len(self.calls) + 1}"
        self.calls.append({"op": "new_surface", "cwd": cwd, "command": command, "name": name, "ref": ref})
        return ref

    def new_surface_in_pane(self, pane_ref: Any, cwd: Any = None,
                            command: Any = None, name: Any = None) -> str:
        ref = f"surface:{len(self.calls) + 1}"
        self.calls.append({"op": "new_surface_in_pane", "cwd": cwd, "command": command, "name": name, "ref": ref})
        return ref

    def surface_to_pane(self, surface_ref: str) -> str:
        return "pane:1"

    def new_persona_surface(self, cwd: Any = None, command: Any = None,
                            name: Any = None, **_: Any) -> str:
        ref = f"surface:{len(self.calls) + 1}"
        self.calls.append({"op": "new_persona_surface", "cwd": cwd, "command": command, "name": name, "ref": ref})
        return ref

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})

    def read_screen(self, ref: str, lines: int = 50) -> str:
        return ""

    def send(self, ref: str, text: str) -> None:
        pass

    def send_key(self, ref: str, key: str) -> None:
        pass

    def paste_text(self, ref: str, text: str) -> None:
        pass

    def list_workspaces(self) -> list[str]:
        return []

    def close(self, ref: str) -> None:
        pass


_SPAWN_OPS = ("new_workspace", "new_surface", "new_surface_in_pane", "new_persona_surface")


def test_routing_test_exercises_dispatch_without_multiplexer_spawn(tmp_path, monkeypatch):
    """Running the bare-number routing test must create zero real workspaces."""
    from atdd.coach.commands import spawn as cmd_spawn_mod
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.utils import multiplexer as mux_mod
    from atdd.train import issue_runner as issue_runner_mod

    spy = _SpyMultiplexer()

    # Inject the spy at every seam a multiplexer could be resolved from, so the
    # real cmux binary is unreachable even on an operator machine that has it.
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: spy)
    monkeypatch.setattr(mux_mod, "get_multiplexer", lambda preferred=None: spy)
    monkeypatch.setattr(mux_mod, "detect_multiplexer", lambda: None)

    # Sandbox the spawn handler's I/O so nothing escapes tmp_path.
    worktree = tmp_path / "wt"
    worktree.mkdir()
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: worktree)
    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "stub prompt")
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")

    # The cold-start watcher loop blocks until a terminal state is reached; the
    # routing test only asserts CLI dispatch, so neutralize the event loop to
    # keep this test bounded. Patch at the canonical home
    # (atdd.train.issue_runner) rather than the deprecated coach.py shim
    # being removed in #923.
    monkeypatch.setattr(issue_runner_mod, "_process_watcher_events", lambda *a, **k: None)

    # Keep all coach runtime artifacts (.atdd/runtime) inside tmp_path.
    monkeypatch.chdir(tmp_path)

    from atdd.coach.commands.tests import (
        test_e002_integration_001_cli_dispatch_routes_review as routing_mod,
    )

    routing_cls = getattr(routing_mod, "TestCliDispatchRoutesReview", None)
    assert routing_cls is not None, (
        "TestCliDispatchRoutesReview missing from "
        "test_e002_integration_001_cli_dispatch_routes_review.py — the routing "
        "test this acceptance covers has moved or been renamed."
    )
    routing_fn = getattr(routing_cls, "test_existing_coach_number_invocation_not_broken", None)
    assert routing_fn is not None, (
        "test_existing_coach_number_invocation_not_broken missing from "
        "TestCliDispatchRoutesReview — the routing test this acceptance covers "
        "has moved or been renamed."
    )

    routing_tmp = tmp_path / "routing_tmp"
    routing_tmp.mkdir()

    # Execute the routing test exactly as pytest would. It internally asserts
    # run_cli returns 0 (bare number still routes to the coach, not the review
    # or status subcommand) — that assertion holds for both the leaky form and
    # the hermetic --dry-run form, so it is not the discriminator here.
    routing_fn(routing_cls(), routing_tmp)

    spawn_ops = [c for c in spy.calls if c["op"] in _SPAWN_OPS]
    assert spawn_ops == [], (
        "test_existing_coach_number_invocation_not_broken spawned a real "
        f"multiplexer workspace/surface: {spawn_ops}.\n"
        "The routing test must exercise CLI dispatch hermetically — via "
        "coach.run_cli(['358', '--dry-run']) or an injected stub multiplexer — "
        "not the real coach, which spawns and leaks an ATDD358 cmux workspace."
    )


def test_routing_test_creates_no_atdd_workspace_outside_tmp_path(tmp_path, monkeypatch):
    """No ATDD<issue> directory or runtime artifact escapes the test sandbox."""
    from atdd.coach.commands import spawn as cmd_spawn_mod
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.utils import multiplexer as mux_mod
    from atdd.train import issue_runner as issue_runner_mod

    spy = _SpyMultiplexer()
    monkeypatch.setattr(cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: spy)
    monkeypatch.setattr(mux_mod, "get_multiplexer", lambda preferred=None: spy)
    monkeypatch.setattr(mux_mod, "detect_multiplexer", lambda: None)

    worktree = tmp_path / "wt"
    worktree.mkdir()
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: worktree)
    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "stub prompt")
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", tmp_path / ".atdd" / "runtime")
    # Patch at the canonical home (atdd.train.issue_runner) rather than the
    # deprecated coach.py shim being removed in #923.
    monkeypatch.setattr(issue_runner_mod, "_process_watcher_events", lambda *a, **k: None)
    monkeypatch.chdir(tmp_path)

    from atdd.coach.commands.tests import (
        test_e002_integration_001_cli_dispatch_routes_review as routing_mod,
    )

    routing_tmp = tmp_path / "routing_tmp"
    routing_tmp.mkdir()
    routing_mod.TestCliDispatchRoutesReview().test_existing_coach_number_invocation_not_broken(
        routing_tmp
    )

    # The spy records the workspace name the coach would have created. A
    # hermetic routing test resolves no multiplexer at all, so no ATDD-named
    # workspace is ever requested.
    atdd_named = [
        c for c in spy.calls
        if c["op"] in _SPAWN_OPS and "ATDD" in str(c.get("name") or "")
    ]
    assert atdd_named == [], (
        f"The routing test requested ATDD-named cmux workspace(s): {atdd_named}. "
        "It must not spawn a real workspace for a closed fixture issue."
    )
