# URN: test:mediate-worker-decisions:coach-runtime:M004-SMOKE-001-real-spawn-captures-daemon-output-to-log
# Acceptance: acc:mediate-worker-decisions:M004-SMOKE-001-real-spawn-captures-daemon-output-to-log
# WMBT: wmbt:mediate-worker-decisions:M004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""M004-SMOKE-001 — a real detached spawn captures its output to daemon.log.

Process-level smoke (no cmux/claude needed, safe anywhere): spawn a REAL child
process via the production ``SubprocessDaemonSpawner`` with a durable ``log_path``
and assert its stdout lands in the on-disk ``daemon.log`` — proving the managed
daemon's runtime output is captured for diagnosis instead of discarded to
``/dev/null`` (the #1007 invisibility bug). Evidence: the log file contents.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
    SubprocessDaemonSpawner,
)

_MARKER = "M004_SMOKE_DAEMON_LOG_MARKER"


def test_m004_smoke_001_real_spawn_captures_daemon_output_to_log(tmp_path):
    log_path = tmp_path / "ws" / "daemon.log"  # parent created by the spawner
    argv = [sys.executable, "-c", f"import sys; sys.stdout.write({_MARKER!r}); sys.stdout.flush()"]

    pid = SubprocessDaemonSpawner().spawn(argv, log_path=str(log_path))
    assert pid > 0

    # the child is detached; wait briefly for it to write + exit
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if log_path.exists() and _MARKER in log_path.read_text(encoding="utf-8"):
            break
        time.sleep(0.1)

    assert log_path.exists(), "daemon.log was never created (output went to /dev/null?)"
    assert _MARKER in log_path.read_text(encoding="utf-8"), (
        "the detached child's stdout was not captured to the durable daemon.log"
    )
