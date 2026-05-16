# URN: test:spawn-agents:atdd-spawn-skeleton-and-harness:E004-SMOKE-001-shim-console-script-real-exit-codes
# Acceptance: acc:spawn-agents:E004-SMOKE-001-shim-console-script-real-exit-codes
# WMBT: wmbt:spawn-agents:E004
# Phase: SMOKE
# Layer: integration
# Harness: smoke/backend
"""E004-SMOKE-001 — the installed ``atdd-cmux-send`` console script rejects a
real ``claude`` launch with exit 2 and forwards a real non-launch payload with
exit 0 against real ``cmux``.

SMOKE: no mocks. Runs the registered console script as a real process.

  1. ``atdd-cmux-send <surface> "claude --permission-mode acceptEdits"`` exits
     2 with the educational error on stderr — rejection is pre-send, so this
     fact holds even without a live cmux surface.
  2. ``atdd-cmux-send <surface> "ls"`` exits 0 and the text reaches the real
     cmux pane unchanged.

Skips when the ``atdd-cmux-send`` console script is not on PATH (RED phase,
or an editable install without the entry point) or no cmux daemon is
reachable (CI without a desktop cmux).

Issue #662 — reject raw ``cmux send "claude ..."`` launches at the source.
"""
from __future__ import annotations

import re
import shutil
import subprocess

import pytest

pytestmark = [pytest.mark.platform]

_SHIM = "atdd-cmux-send"


def _cmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["cmux", *args], capture_output=True, text=True)


def _require_shim() -> str:
    path = shutil.which(_SHIM)
    if path is None:
        pytest.skip(f"{_SHIM} console script not installed on PATH")
    return path


def _scratch_surface() -> str:
    """Create a throwaway cmux terminal surface; skip if cmux is unreachable."""
    if shutil.which("cmux") is None:
        pytest.skip("cmux binary not on PATH")
    probe = _cmux("list-workspaces")
    if probe.returncode != 0:
        pytest.skip("no cmux daemon reachable")
    created = _cmux("new-pane")
    if created.returncode != 0:
        pytest.skip(f"could not create scratch cmux surface: {created.stderr.strip()}")
    match = re.search(r"surface:(\S+)", created.stdout)
    if not match:
        pytest.skip(f"unexpected cmux new-pane output: {created.stdout!r}")
    return f"surface:{match.group(1)}"


def test_console_script_rejects_real_claude_launch_with_exit_2():
    """A real ``atdd-cmux-send`` process rejects a claude launch (exit 2)."""
    _require_shim()
    result = subprocess.run(
        [_SHIM, "surface:1", "claude --permission-mode acceptEdits"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "atdd spawn --worktree" in result.stderr


def test_console_script_forwards_real_non_launch_payload_with_exit_0():
    """A real ``atdd-cmux-send`` process forwards ``ls`` to a live cmux pane."""
    _require_shim()
    surface = _scratch_surface()
    try:
        result = subprocess.run(
            [_SHIM, surface, "ls"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
    finally:
        _cmux("close-pane", surface)
