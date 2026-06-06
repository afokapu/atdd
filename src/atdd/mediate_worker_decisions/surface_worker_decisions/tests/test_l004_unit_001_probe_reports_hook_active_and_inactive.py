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

import shutil
import socket
import tempfile

from atdd.mediate_worker_decisions.surface_worker_decisions.src.integration.cmux_hook_probe import (
    CmuxHookProbe,
)


def test_probe_active_with_surface_and_live_socket():
    # macOS caps AF_UNIX bind() paths at ~104 chars, which pytest's deep tmp_path
    # blows past. Bind under a short mkdtemp dir instead; the probe stat()s the
    # path (not subject to the bind cap) so the active verdict still holds.
    sock_dir = tempfile.mkdtemp(prefix="cmuxsk-")
    sock_path = f"{sock_dir}/s.sock"
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(1)
    try:
        probe = CmuxHookProbe(
            env={"CMUX_SURFACE_ID": "S1", "CMUX_SOCKET_PATH": sock_path}
        )
        presence = probe.evaluate()
        assert presence.active is True
    finally:
        srv.close()
        shutil.rmtree(sock_dir, ignore_errors=True)


def test_probe_inactive_names_missing_surface_id(tmp_path):
    probe = CmuxHookProbe(env={"CMUX_SOCKET_PATH": str(tmp_path / "cmux.sock")})
    presence = probe.evaluate()
    assert presence.active is False
    assert "CMUX_SURFACE_ID" in presence.reason
