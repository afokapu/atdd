# URN: test:mediate-worker-decisions:coach-runtime:M004-SMOKE-001-real-spawn-captures-daemon-output-to-log
# Acceptance: acc:mediate-worker-decisions:M004-SMOKE-001-real-spawn-captures-daemon-output-to-log
# WMBT: wmbt:mediate-worker-decisions:M004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""M004-SMOKE-001 — a real surface launch captures its output to daemon.log.

Integration smoke: launch a REAL cmux surface via the production
``CmuxSurfaceDaemonLauncher`` running a command that prints a known marker, with a
durable ``log_path``, and assert the marker lands in the on-disk ``daemon.log`` —
proving the managed daemon's runtime output is captured for diagnosis (the #1007
invisibility bug) even though the daemon now runs inside a cmux surface rather than
a ``subprocess.Popen``. Skips cleanly when cmux is absent. Evidence: the log file.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)

_MARKER = "M004_SMOKE_DAEMON_LOG_MARKER"


def test_m004_smoke_001_real_spawn_captures_daemon_output_to_log(tmp_path):
    from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
        CmuxSurfaceDaemonLauncher,
        CmuxWorkspaceCloser,
    )

    log_path = tmp_path / "ws" / "daemon.log"  # parent created by the launcher
    launcher = CmuxSurfaceDaemonLauncher(cwd=str(tmp_path))

    daemon_ws = launcher.spawn(
        ["printf", f"{_MARKER}\\n"],
        name="atdd-coach-daemon-m004-smoke",
        log_path=str(log_path),
    )
    assert daemon_ws.startswith("workspace:")

    try:
        deadline = time.time() + 15.0
        while time.time() < deadline:
            if log_path.exists() and _MARKER in log_path.read_text(encoding="utf-8"):
                break
            time.sleep(0.2)

        assert log_path.exists(), "daemon.log was never created (output not captured)"
        assert _MARKER in log_path.read_text(encoding="utf-8"), (
            "the surface command's stdout was not captured to the durable daemon.log"
        )
    finally:
        CmuxWorkspaceCloser().close(daemon_ws)
