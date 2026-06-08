# URN: test:mediate-worker-decisions:coach-runtime:M005-UNIT-002-spawn-env-scrubs-stale-cmux-client-context-vars
# Acceptance: acc:mediate-worker-decisions:M005-UNIT-002-spawn-env-scrubs-stale-cmux-client-context-vars
# WMBT: wmbt:mediate-worker-decisions:M005
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""M005-UNIT-002 — the daemon spawn scrubs the stale cmux client-context env.

``atdd coach start`` spawns the feed_daemon DETACHED; without an explicit env the
child inherits the coach session's stale cmux CLIENT-CONTEXT vars (``CMUX_PANEL_ID``,
an empty ``CMUX_SOCKET``, ``CMUX_SURFACE_ID``, ``CMUX_AGENT_*``) and its ``cmux rpc``
calls then break-pipe against the dead surface/socket (the #1007 reopen). The spawner
must hand ``Popen`` an explicit env with those vars scrubbed, while preserving ``PATH``
and ``CMUX_BUNDLED_CLI_PATH`` so cmux still finds its own bundled CLI + default socket.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.coach_runtime.src.integration import daemon_manager
from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
    SubprocessDaemonSpawner,
)


class _FakePopen:
    instances = []

    def __init__(self, argv, **kwargs):
        self.argv = argv
        self.kwargs = kwargs
        self.pid = 4242
        _FakePopen.instances.append(self)


def test_spawn_env_scrubs_stale_cmux_client_context_vars(tmp_path, monkeypatch):
    _FakePopen.instances.clear()
    monkeypatch.setattr(daemon_manager.subprocess, "Popen", _FakePopen)

    # A coach session's environment: stale per-surface/panel/socket cmux identity,
    # plus the two things cmux legitimately needs to find itself.
    monkeypatch.setenv("CMUX_PANEL_ID", "panel-7")
    monkeypatch.setenv("CMUX_SOCKET", "")  # the empty-socket trap from the live repro
    monkeypatch.setenv("CMUX_SURFACE_ID", "surface-9")
    monkeypatch.setenv("CMUX_AGENT_ID", "agent-3")
    monkeypatch.setenv("CMUX_BUNDLED_CLI_PATH", "/opt/cmux/bin/cmux")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    log_path = tmp_path / "ws" / "daemon.log"
    pid = SubprocessDaemonSpawner().spawn(["true"], log_path=str(log_path))

    assert pid == 4242
    assert len(_FakePopen.instances) == 1
    env = _FakePopen.instances[0].kwargs.get("env")

    # An EXPLICIT env was passed (not None → not raw inheritance of the stale vars).
    assert env is not None, "spawn must pass an explicit scrubbed env, not inherit it"

    # Every stale cmux client-context var is gone.
    for stale in ("CMUX_PANEL_ID", "CMUX_SOCKET", "CMUX_SURFACE_ID", "CMUX_AGENT_ID"):
        assert stale not in env, f"{stale} must be scrubbed from the daemon's env"
    assert not any(
        k.startswith("CMUX_AGENT_") for k in env
    ), "all CMUX_AGENT_* client identity must be scrubbed"

    # The two things cmux needs to find itself survive untouched.
    assert env.get("CMUX_BUNDLED_CLI_PATH") == "/opt/cmux/bin/cmux"
    assert env.get("PATH") == "/usr/bin:/bin"
