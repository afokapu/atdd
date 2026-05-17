# URN: test:review-phase-boundaries:phase-boundary-review:E004-SMOKE-001-coach-suite-no-real-cmux-workspace-leak
# Acceptance: acc:review-phase-boundaries:E004-INTEGRATION-001-coach-suite-run-creates-zero-cmux-workspaces
# WMBT: wmbt:review-phase-boundaries:E004
# Phase: SMOKE
# Layer: backend.integration
# Runtime: python
# Smoke: true
# Purpose: Verify the coach leak module is hermetic against the REAL cmux multiplexer — zero workspaces, zero observer processes leaked
"""E004-SMOKE-001 — coach leak module leaks nothing against the real cmux.

The RED-first regression guard (E004-INTEGRATION-001) shadows ``cmux`` with a
recording shim, so it proves the *coach* never issues a workspace verb. This
smoke test removes the shim: it runs the known leak module —
``test_e002_integration_001_cli_dispatch_routes_review.py`` — against the
operator's **real** ``cmux`` binary and the **real** ``atdd observer`` process
table, then asserts the live workspace list and observer-process count are
unchanged.

That is the SMOKE contract: contract/integration tests verify the coach's
*intent* (it never calls a spawn verb); this verifies the *outcome* against
real infrastructure (no ``ATDD358`` workspace or zombie observer materialises).

Before the GREEN fix the leak module called ``coach.run_cli(["358"])`` with no
``--dry-run``; the real coach resolved the real cmux backend and spawned a real
``ATDD358`` workspace + observer that nothing tore down — this test would FAIL
with a non-empty workspace/observer delta. After the fix the routing test uses
``--dry-run`` and the coach short-circuits before touching the multiplexer.

Skips cleanly where ``cmux`` is not on PATH (CI), so it never blocks the unit
suite. Bounded to the named leak module — matching E004-INTEGRATION-001 — so
the smoke run stays deterministic and never exercises unrelated coach tests
against the operator's live session.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

# tests/ → commands/ → coach/ → atdd/ → src/ → repo root
_REPO_ROOT = Path(__file__).resolve().parents[5]
_SRC_ROOT = _REPO_ROOT / "src"
_LEAK_MODULE = (
    _SRC_ROOT
    / "atdd/coach/commands/tests"
    / "test_e002_integration_001_cli_dispatch_routes_review.py"
)

# A non-hermetic coach hangs in the watcher event loop after a leaking spawn;
# the workspace would already exist by the time the timeout fires, which the
# post-run snapshot still catches.
_SUITE_TIMEOUT_S = 120


def _cmux_workspace_refs() -> set[str]:
    """Snapshot of live cmux workspace refs (``workspace:N`` tokens)."""
    result = subprocess.run(
        ["cmux", "list-workspaces"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, (
        f"`cmux list-workspaces` failed: {result.stderr or result.stdout}"
    )
    refs: set[str] = set()
    for line in result.stdout.splitlines():
        for token in line.split():
            if token.startswith("workspace:"):
                refs.add(token)
    return refs


def _observer_pids() -> set[int]:
    """Snapshot of live ``atdd observer run`` process PIDs."""
    result = subprocess.run(
        ["ps", "-eo", "pid=,command="],
        capture_output=True, text=True, timeout=10,
    )
    pids: set[int] = set()
    for line in result.stdout.splitlines():
        if "observer run" not in line:
            continue
        head = line.split(None, 1)
        if head and head[0].isdigit():
            pids.add(int(head[0]))
    return pids


@pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="real cmux multiplexer not on PATH — smoke test needs live infrastructure",
)
def test_coach_leak_module_creates_zero_real_cmux_workspaces(tmp_path):
    """The fixed leak module spawns no real cmux workspace or observer."""
    assert _LEAK_MODULE.is_file(), f"Coach leak module not found: {_LEAK_MODULE}"

    workspaces_before = _cmux_workspace_refs()
    observers_before = _observer_pids()

    env = dict(os.environ)
    env["PYTHONPATH"] = f"{_SRC_ROOT}{os.pathsep}{env.get('PYTHONPATH', '')}"

    run_dir = tmp_path / "run"
    run_dir.mkdir()

    timed_out = False
    try:
        subprocess.run(
            [
                sys.executable, "-m", "pytest",
                str(_LEAK_MODULE),
                "-p", "no:cacheprovider",
                "-q",
            ],
            env=env,
            cwd=run_dir,
            timeout=_SUITE_TIMEOUT_S,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        # A non-hermetic coach hangs after the leaking spawn; the leaked
        # workspace is already live and the snapshot below still catches it.
        timed_out = True

    workspaces_after = _cmux_workspace_refs()
    observers_after = _observer_pids()

    new_workspaces = workspaces_after - workspaces_before
    leaked_observers = observers_after - observers_before

    # Teardown: close anything the run leaked so the smoke test never adds to
    # the operator's ghost-workspace pile, even on failure.
    for ref in new_workspaces:
        subprocess.run(
            ["cmux", "close-workspace", "--workspace", ref],
            capture_output=True, text=True, timeout=15,
        )
    for pid in leaked_observers:
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            pass

    assert not new_workspaces, (
        f"The coach leak module spawned {len(new_workspaces)} real cmux "
        f"workspace(s) {sorted(new_workspaces)} against the live multiplexer "
        "(now closed). Coach tests must be hermetic — route via --dry-run or "
        "an injected stub multiplexer, never the real coach."
    )
    assert not leaked_observers, (
        f"The coach leak module leaked {len(leaked_observers)} `atdd observer "
        f"run` process(es) {sorted(leaked_observers)} (now signalled). Every "
        "coach test must tear down anything it spawns."
    )
    assert not timed_out, (
        "The coach leak module run timed out — a hermetic --dry-run "
        "invocation returns immediately; a hang implies the real coach "
        "watcher loop was entered."
    )
