# URN: test:spawn-agents:transactional-spawn-and-orphan-pane-gc:E003-INTEGRATION-001-spawn-failure-cleans-pane
# Acceptance: acc:spawn-agents:E003-INTEGRATION-001-spawn-failure-cleans-pane
# WMBT: wmbt:spawn-agents:E003
# Phase: RED
# Layer: integration
"""E003-INTEGRATION-001 — a failed spawn step closes the pane it created.

`CmuxBackend.new_surface` (new-pane branch): `cmux new-pane` creates the
pane and echoes `OK surface:N pane:M workspace:K`; the surface ref is read
straight from that output (no `cmux list-pane-surfaces` round-trip — that
call needs --workspace and, when it failed, stranded the just-created pane
outside the guard, #655 SMOKE bug 4). The rename + seed steps then run
inside a transactional guard: ANY failure closes the surface — scoped with
`--workspace` so the short ref resolves — before the error propagates, so
the failed spawn leaves zero orphan panes.

cmux contract: the mocked `_run` returns the REAL cmux 0.63.2 output
shapes captured live during the #655 SMOKE run. A raised `MultiplexerError`
faithfully simulates a real `cmux` command exiting non-zero (`_run` raises
`MultiplexerError` on `CalledProcessError`) — e.g. `cmux send` against a
non-terminal surface, verified live as `invalid_params: Surface is not a
terminal`.

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
    """A failed `cmux send` (seed step) must trigger a `cmux close-surface`
    — scoped with --workspace — for the pane created in the same attempt."""
    backend = CmuxBackend()
    calls: list[list[str]] = []

    def fake_run(cmd, capture=True):
        calls.append(list(cmd))
        # Pane creation succeeds — `cmux new-pane` echoes every ref we need.
        if cmd[:2] == ["cmux", "new-pane"]:
            return _ok("OK surface:441 pane:77 workspace:1\n")
        if cmd[:2] == ["cmux", "rename-tab"]:
            return _ok("OK action=rename tab=tab:441 workspace=workspace:1\n")
        # The seed step fails for real — simulates `cmux send` exiting non-zero.
        if cmd[:2] == ["cmux", "send"]:
            raise MultiplexerError(
                "cmux send --surface surface:441 failed (exit 1): "
                "Error: invalid_params: Surface is not a terminal"
            )
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

    # #655 bug 4: new_surface must NOT make the `list-pane-surfaces` round-trip.
    assert not any(c[:2] == ["cmux", "list-pane-surfaces"] for c in calls), (
        "new_surface still calls `cmux list-pane-surfaces` — the surface ref "
        f"must be read from the new-pane output instead. calls: {calls}"
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

    closed = close_calls[0]
    assert "surface:441" in closed, (
        f"the close call did not target the created surface:441: {closed}"
    )
    # The close must be scoped to the owning workspace — an unscoped
    # `cmux close-surface` resolves against the selected workspace only
    # and fails with "Surface not found" (#655 SMOKE bug 2).
    assert "--workspace" in closed and "workspace:1" in closed, (
        f"close-surface must be scoped with `--workspace workspace:1`: {closed}"
    )


def test_failed_rename_closes_the_created_pane():
    """A failure anywhere in the post-`new-pane` window — here `cmux
    rename-tab` — must also close the created pane. The transactional guard
    covers the WHOLE window after the pane exists, not just the seed step."""
    backend = CmuxBackend()
    calls: list[list[str]] = []

    def fake_run(cmd, capture=True):
        calls.append(list(cmd))
        if cmd[:2] == ["cmux", "new-pane"]:
            return _ok("OK surface:512 pane:88 workspace:1\n")
        # The rename step fails for real — simulates `cmux rename-tab`
        # exiting non-zero immediately after the pane was created.
        if cmd[:2] == ["cmux", "rename-tab"]:
            raise MultiplexerError(
                "cmux rename-tab --surface surface:512 failed (exit 1): "
                "Error: not_found: Tab not found"
            )
        if cmd[:2] == ["cmux", "close-surface"]:
            return _ok("OK surface:512 workspace:1\n")
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
        "orphan pane leaked: `cmux rename-tab` failed right after the pane "
        f"was created but no `cmux close-*` was issued. cmux calls: {calls}"
    )
    closed = close_calls[0]
    assert "surface:512" in closed, (
        f"close call did not target the created surface:512: {closed}"
    )
    assert "--workspace" in closed and "workspace:1" in closed, (
        f"close-surface must be scoped with `--workspace workspace:1`: {closed}"
    )
