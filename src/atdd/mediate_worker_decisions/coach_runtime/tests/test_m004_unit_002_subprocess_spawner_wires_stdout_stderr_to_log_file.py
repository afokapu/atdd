# URN: test:mediate-worker-decisions:coach-runtime:M004-UNIT-002-subprocess-spawner-wires-stdout-stderr-to-log-file
# Acceptance: acc:mediate-worker-decisions:M004-UNIT-002-subprocess-spawner-wires-stdout-stderr-to-log-file
# WMBT: wmbt:mediate-worker-decisions:M004
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""M004-UNIT-002 — the surface launcher redirects daemon stdout/stderr to daemon.log.

Since #1007 the daemon runs inside a cmux surface (``cmux new-workspace --command``),
not a ``subprocess.Popen``. To preserve the M004 observability guarantee, the launcher
must build a ``--command`` that redirects the daemon's stdout AND stderr to the durable
``daemon.log`` (``>> <log> 2>&1``) — so a runtime failure leaves a diagnosable trace
instead of vanishing into the surface pane — and create the log directory if missing.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
    CmuxSurfaceDaemonLauncher,
)


class _RecordingRunner:
    """Captures the cmux argv and returns a new-workspace ref."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(list(args))
        return "workspace:7"


def test_surface_launcher_redirects_stdout_stderr_to_log_file(tmp_path):
    runner = _RecordingRunner()
    log_path = tmp_path / "nested" / "daemon.log"  # parent does not exist yet

    ref = CmuxSurfaceDaemonLauncher(cwd=str(tmp_path), runner=runner).spawn(
        ["python", "-m", "feed_daemon", "--workspace", "ws-1"],
        name="atdd-coach-daemon-ws-1",
        log_path=str(log_path),
    )

    assert ref == "workspace:7"
    assert len(runner.calls) == 1
    argv = runner.calls[0]
    assert argv[0] == "new-workspace"
    assert "--focus" in argv and argv[argv.index("--focus") + 1] == "false"

    # The --command redirects BOTH stdout and stderr to the durable daemon.log.
    command = argv[argv.index("--command") + 1]
    assert f">> {log_path}" in command or str(log_path) in command
    assert "2>&1" in command, "stderr must share the daemon log with stdout"

    # The log directory was created on disk (not left to /dev/null).
    assert log_path.parent.exists()
