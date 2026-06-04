# URN: test:mediate-worker-decisions:surface-worker-decisions:L004-UNIT-001-probe-reports-hook-active-and-inactive
# Acceptance: acc:mediate-worker-decisions:L004-UNIT-001-probe-reports-hook-active-and-inactive
# WMBT: wmbt:mediate-worker-decisions:L004
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""L004-UNIT-001 — the hook-presence probe reports active vs inactive with a reason.

With CMUX_SURFACE_ID set and a live socket the probe reports the hook path active;
with the surface id absent it reports inactive and names the missing precondition.
"""
from __future__ import annotations

import socket

from atdd.mediate_worker_decisions.surface_worker_decisions.src.integration.cmux_hook_probe import (
    CmuxHookProbe,
)


def test_probe_active_with_surface_and_live_socket(tmp_path):
    sock_path = tmp_path / "cmux.sock"
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(sock_path))
    srv.listen(1)
    try:
        probe = CmuxHookProbe(
            env={"CMUX_SURFACE_ID": "S1", "CMUX_SOCKET_PATH": str(sock_path)}
        )
        presence = probe.evaluate()
        assert presence.active is True
    finally:
        srv.close()


def test_probe_inactive_names_missing_surface_id(tmp_path):
    probe = CmuxHookProbe(env={"CMUX_SOCKET_PATH": str(tmp_path / "cmux.sock")})
    presence = probe.evaluate()
    assert presence.active is False
    assert "CMUX_SURFACE_ID" in presence.reason
