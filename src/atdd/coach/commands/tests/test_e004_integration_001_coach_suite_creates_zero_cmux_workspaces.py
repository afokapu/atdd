# URN: test:review-phase-boundaries:phase-boundary-review:E004-INTEGRATION-001-coach-suite-run-creates-zero-cmux-workspaces
# Acceptance: acc:review-phase-boundaries:E004-INTEGRATION-001-coach-suite-run-creates-zero-cmux-workspaces
# WMBT: wmbt:review-phase-boundaries:E004
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: Running the coach test suite creates zero new cmux workspaces and leaves no observer process alive — the RED-first regression that proves the leak is closed
"""RED Test for test:review-phase-boundaries:phase-boundary-review:E004-INTEGRATION-001-coach-suite-run-creates-zero-cmux-workspaces
wagon: review-phase-boundaries | feature: phase-boundary-review | phase: RED
WMBT: wmbt:review-phase-boundaries:E004

Purpose
-------
The dynamic regression guard. The ``cmux`` executable on PATH is shadowed by a
recording shim that appends every invocation to a log file instead of spawning
a real workspace. The coach command test module that contains the leak —
``test_e002_integration_001_cli_dispatch_routes_review.py`` — is then run as a
subprocess under that shim.

A hermetic coach test suite touches the multiplexer not at all. So after the
run the shim log must contain zero workspace-creating verbs
(``new-workspace`` / ``new-pane`` / ``new-surface``), and no ``atdd observer
run`` process must have been leaked.

RED-first: before the hermeticity fix the leaky routing test invokes the real
coach, which resolves the (shimmed) cmux backend and issues
``cmux new-workspace`` for an ``ATDD358`` workspace — the shim records it →
this test FAILS. After the fix the routing test uses ``--dry-run``; the coach
short-circuits before resolving any multiplexer → the shim log holds no
workspace verb → this test PASSES.

Scope note: this exercises the known leak module specifically (rather than the
whole ``commands/tests/`` directory) so the test stays bounded and
deterministic. The suite-wide static guarantee is carried by the AST audit
(E004-UNIT-002); this test is the behavioral proof that the named leak is shut.
"""
from __future__ import annotations

import os
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

# A POSIX-sh recording shim. It logs every invocation, then emits just enough
# stdout for the cmux backend's ref parsing to succeed — it never spawns a
# real workspace, so even a non-hermetic test cannot leak under it.
_SHIM_SCRIPT = """#!/bin/sh
# Recording cmux shim — records invocations, never spawns a real workspace.
printf '%s\\n' "$*" >> "$CMUX_SHIM_LOG"
case "$1" in
  new-workspace)      echo "OK workspace:1" ;;
  new-pane)           echo "OK pane:1" ;;
  new-surface)        echo "OK surface:1" ;;
  list-pane-surfaces) echo "OK surface:1" ;;
  list-panes)         echo "OK pane:1" ;;
  list-workspaces)    echo "workspace:1" ;;
  --version)          echo "cmux 0.0.0-shim" ;;
  *)                  : ;;
esac
exit 0
"""

# Subprocess budget: a non-hermetic coach hangs in the watcher event loop after
# the leaking spawn. By the time the timeout fires the shim has long since
# recorded the workspace creation — the recording is what this test inspects.
_SUITE_TIMEOUT_S = 120

_WORKSPACE_VERBS = ("new-workspace", "new-pane", "new-surface")


def _observer_pids() -> set[int]:
    """Best-effort snapshot of live ``atdd observer run`` process PIDs."""
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,command="],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:  # noqa: BLE001 — process listing is best-effort
        return set()
    pids: set[int] = set()
    for line in result.stdout.splitlines():
        if "atdd observer run" not in line and "observer run" not in line:
            continue
        head = line.split(None, 1)
        if head and head[0].isdigit():
            pids.add(int(head[0]))
    return pids


def test_coach_command_suite_run_creates_zero_cmux_workspaces(tmp_path):
    """Running the coach leak module records zero cmux workspace creations."""
    assert _LEAK_MODULE.is_file(), (
        f"Coach leak module not found: {_LEAK_MODULE}"
    )

    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    shim_log = tmp_path / "cmux-invocations.log"
    shim_path = shim_dir / "cmux"
    shim_path.write_text(_SHIM_SCRIPT)
    shim_path.chmod(0o755)

    observers_before = _observer_pids()

    env = dict(os.environ)
    env["PATH"] = f"{shim_dir}{os.pathsep}{env.get('PATH', '')}"
    env["CMUX_SHIM_LOG"] = str(shim_log)
    env["PYTHONPATH"] = f"{_SRC_ROOT}{os.pathsep}{env.get('PYTHONPATH', '')}"

    run_dir = tmp_path / "run"
    run_dir.mkdir()

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
        # Expected while the suite is non-hermetic: the real coach hangs in the
        # watcher loop after the leaking spawn. The shim log already holds the
        # recorded workspace creation.
        pass

    observers_after = _observer_pids()

    log_lines = []
    if shim_log.exists():
        log_lines = [ln for ln in shim_log.read_text().splitlines() if ln.strip()]
    workspace_creates = [
        ln for ln in log_lines
        if ln.split() and ln.split()[0] in _WORKSPACE_VERBS
    ]

    assert workspace_creates == [], (
        f"The coach command test suite created {len(workspace_creates)} cmux "
        "workspace/pane/surface(s) via the real multiplexer:\n  "
        + "\n  ".join(workspace_creates)
        + "\nCoach tests must be hermetic — exercise CLI routing via --dry-run "
        "or an injected stub multiplexer, never the real coach."
    )

    leaked_observers = observers_after - observers_before
    assert not leaked_observers, (
        "The coach test suite leaked observer process(es) "
        f"(pids {sorted(leaked_observers)}) — every coach test must tear down "
        "anything it spawns."
    )
