# URN: test:spawn-agents:transactional-spawn-and-orphan-pane-gc:E003-SMOKE-001-spawn-failure-cleans-pane
# Acceptance: acc:spawn-agents:E003-INTEGRATION-001-spawn-failure-cleans-pane
# WMBT: wmbt:spawn-agents:E003
# Phase: SMOKE
# Layer: integration
# Harness: smoke/backend
"""E003-SMOKE-001 — transactional spawn pipeline verified against REAL cmux.

SMOKE: no mocks. Exercises Layer 1 against a live cmux daemon in a
throwaway scratch workspace (never workspace:1; closed afterwards).

Two facts are verified against real cmux 0.63.2:

1. `CmuxBackend.new_surface` against a NON-selected workspace creates
   exactly one pane and leaves no orphan. This is the #655 bug-4
   regression guard — before the --workspace sweep, `new_surface` raised
   at `cmux list-pane-surfaces --pane` and stranded the just-created pane.

2. A real spawn-step failure leaves zero orphans: a genuine `cmux send`
   failure (sending to a browser surface — real cmux rejects it with
   `invalid_params: Surface is not a terminal`) followed by the real
   transactional cleanup (`CmuxBackend.close(..., workspace=ws)`) removes
   the half-created pane. No mock injects the failure — it is a real
   cmux error.

Skips when no cmux daemon is reachable (CI without a desktop cmux).

Issue #655 — Layer 1: transactional spawn pipeline.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import time

import pytest

from atdd.coach.utils.multiplexer import CmuxBackend

pytestmark = [pytest.mark.platform]


def _cmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["cmux", *args], capture_output=True, text=True)


def _require_cmux() -> None:
    if shutil.which("cmux") is None:
        pytest.skip("real cmux daemon not available — SMOKE needs real infrastructure")
    if _cmux("list-workspaces").returncode != 0:
        pytest.skip("cmux is installed but no daemon is reachable")


def _surfaces(workspace: str) -> set[str]:
    out = _cmux("list-panels", "--workspace", workspace).stdout
    return set(re.findall(r"surface:\d+", out))


@pytest.fixture()
def scratch_workspace():
    """A throwaway cmux workspace, closed on teardown. Never workspace:1."""
    _require_cmux()
    out = _cmux("new-workspace", "--name", "ATDD655-smoke-L1", "--cwd", "/tmp").stdout
    match = re.search(r"workspace:\d+", out)
    assert match, f"could not create scratch workspace: {out!r}"
    workspace = match.group(0)
    assert workspace != "workspace:1", "refusing to run SMOKE in workspace:1"
    try:
        yield workspace
    finally:
        _cmux("close-workspace", "--workspace", workspace)


def test_new_surface_leaves_no_orphan_against_real_cmux(scratch_workspace):
    """Real `CmuxBackend.new_surface` against a non-selected workspace
    creates exactly one pane — no stranded orphan (#655 bug-4 regression)."""
    workspace = scratch_workspace
    backend = CmuxBackend()

    before = _surfaces(workspace)
    surface_ref = backend.new_surface(
        workspace_ref=workspace,
        cwd="/tmp",
        command="echo atdd655-smoke",
        name="ATDD655-smoke-pane",
    )
    time.sleep(1)
    created = _surfaces(workspace) - before

    assert created == {surface_ref}, (
        f"new_surface must create exactly one pane ({surface_ref}); real cmux "
        f"shows {created} created — an extra surface is an orphan leak"
    )

    # The real cleanup primitive removes it cleanly.
    backend.close(surface_ref, workspace=workspace)
    time.sleep(1)
    assert surface_ref not in _surfaces(workspace), (
        f"close({surface_ref}, workspace={workspace}) did not remove the pane"
    )


def test_failed_spawn_step_leaves_zero_orphans(scratch_workspace):
    """A real spawn-step failure + the real transactional cleanup leaves
    zero orphan panes in cmux."""
    workspace = scratch_workspace
    backend = CmuxBackend()

    # A real pane created during a spawn attempt.
    new_pane = _cmux("new-pane", "--type", "browser", "--workspace", workspace).stdout
    surface_ref = re.search(r"surface:\d+", new_pane).group(0)
    assert surface_ref in _surfaces(workspace)

    # A genuine spawn-step failure: real cmux rejects `send` to a browser
    # surface. No mock — this is a real `cmux` non-zero exit.
    failed = _cmux("send", "--surface", surface_ref, "--workspace", workspace, "echo x")
    assert failed.returncode != 0, (
        f"expected a real cmux failure, got rc=0: {failed.stdout!r}"
    )
    assert "not a terminal" in (failed.stderr + failed.stdout).lower()

    # The real transactional cleanup closes the half-created pane.
    backend._close_quietly(surface_ref, workspace=workspace)
    time.sleep(1)

    assert surface_ref not in _surfaces(workspace), (
        f"orphan leaked: the half-created pane {surface_ref} survived the "
        f"failed spawn step in real cmux"
    )
