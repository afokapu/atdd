# URN: test:mediate-worker-decisions:coach-runtime:M004-UNIT-002-subprocess-spawner-wires-stdout-stderr-to-log-file
# Acceptance: acc:mediate-worker-decisions:M004-UNIT-002-subprocess-spawner-wires-stdout-stderr-to-log-file
# WMBT: wmbt:mediate-worker-decisions:M004
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""M004-UNIT-002 — the real spawner opens the log file and wires the daemon to it.

``SubprocessDaemonSpawner.spawn(argv, log_path=...)`` must open the durable log for
append and wire the child's stdout AND stderr to that file (so a detached daemon's
runtime failure is captured), with stdin still ``DEVNULL`` — instead of discarding
everything to ``/dev/null``. The log directory is created if missing.
"""
from __future__ import annotations

import subprocess

from atdd.mediate_worker_decisions.coach_runtime.src.integration import daemon_manager
from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
    SubprocessDaemonSpawner,
)


class _FakePopen:
    """Captures the std stream kwargs without launching a process."""

    instances = []

    def __init__(self, argv, **kwargs):
        self.argv = argv
        self.kwargs = kwargs
        self.pid = 9191
        _FakePopen.instances.append(self)


def test_subprocess_spawner_wires_stdout_stderr_to_log_file(tmp_path, monkeypatch):
    _FakePopen.instances.clear()
    monkeypatch.setattr(daemon_manager.subprocess, "Popen", _FakePopen)

    log_path = tmp_path / "nested" / "daemon.log"  # parent does not exist yet
    pid = SubprocessDaemonSpawner().spawn(["true"], log_path=str(log_path))

    assert pid == 9191
    assert len(_FakePopen.instances) == 1
    kwargs = _FakePopen.instances[0].kwargs

    # stdin stays DEVNULL; stdout/stderr go to a real writable file (NOT DEVNULL).
    assert kwargs["stdin"] == subprocess.DEVNULL
    stdout, stderr = kwargs["stdout"], kwargs["stderr"]
    assert stdout is not subprocess.DEVNULL and stdout != subprocess.DEVNULL
    assert hasattr(stdout, "write"), "stdout was not wired to a writable log file"
    assert stderr is stdout, "stderr must share the daemon log with stdout"

    # the log directory was created and the file opened on disk
    assert log_path.exists()
