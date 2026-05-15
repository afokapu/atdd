# URN: test:spawn-agents:transactional-spawn-and-orphan-pane-gc:E003-INTEGRATION-001-spawn-failure-cleans-pane
# Acceptance: acc:spawn-agents:E003-INTEGRATION-001-spawn-failure-cleans-pane
# WMBT: wmbt:spawn-agents:E003
# Phase: RED
# Layer: integration
"""E003-INTEGRATION-001 — a failed spawn step closes the pane it created.

`CmuxBackend.new_surface` runs a multi-step sequence: create the pane,
reuse its default surface, rename it, then seed the surface with the
`cd && claude` command via `cmux send`. When the seed step fails the
pane created earlier in the same attempt MUST be closed before the
error propagates, so the failed spawn leaves zero orphan panes.

RED: today `new_surface` creates the pane unconditionally and never
calls a `cmux close-*` command on the failure path — the pane is
stranded. This test simulates a failed `cmux send` and asserts the
created pane/surface is closed.

Issue #655 — Layer 1: transactional spawn pipeline.
"""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from atdd.coach.utils.multiplexer import CmuxBackend, MultiplexerError

pytestmark = [pytest.mark.platform]


def _ok(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_failed_seed_command_closes_the_created_pane():
    """A failed `cmux send` (seed step) must trigger a `cmux close-*` for
    the pane created earlier in the same `new_surface` attempt."""
    backend = CmuxBackend()
    calls: list[list[str]] = []

    # Return values below are the REAL cmux 0.63.2 output shapes, captured
    # live during the #655 SMOKE run (see commit message). cmux emits short
    # OK-lines; `list-pane-surfaces` lists `surface:N  <cwd>  [selected]`.
    def fake_run(cmd, capture=True):
        calls.append(list(cmd))
        # Pane creation succeeds — the orphan-prone window opens here.
        if cmd[:2] == ["cmux", "new-pane"]:
            return _ok("OK surface:441 pane:77 workspace:1\n")
        if cmd[:2] == ["cmux", "list-pane-surfaces"]:
            return _ok("* surface:441  /tmp  [selected]\n")
        if cmd[:2] == ["cmux", "rename-tab"]:
            return _ok("OK action=rename tab=tab:441 workspace=workspace:1\n")
        # The seed step fails — this is the spawn-step failure being simulated.
        if cmd[:2] == ["cmux", "send"]:
            raise MultiplexerError("simulated failed cmux send")
        if cmd[:2] == ["cmux", "close-surface"]:
            return _ok("OK surface:441 workspace:1\n")
        return _ok("")

    with patch("atdd.coach.utils.multiplexer._run", side_effect=fake_run):
        with pytest.raises(MultiplexerError):
            backend.new_surface(
                workspace_ref="workspace:1",
                cwd="/tmp/feat-coach-spawn-orphan-pane-cleanup",
                command="claude --dangerously-skip-permissions",
                name="ATDD655-coder",
            )

    close_calls = [
        c for c in calls
        if len(c) >= 2 and c[0] == "cmux" and c[1].startswith("close")
    ]
    assert close_calls, (
        "orphan pane leaked: after the seed `cmux send` failed, no `cmux "
        "close-*` command was issued for the pane created earlier in the "
        f"same spawn attempt. cmux calls were: {calls}"
    )

    closed_tokens = {tok for c in close_calls for tok in c}
    assert "surface:441" in closed_tokens or "pane:77" in closed_tokens, (
        "the close call did not target the pane/surface created in this "
        f"attempt (surface:441 / pane:77). close calls: {close_calls}"
    )
