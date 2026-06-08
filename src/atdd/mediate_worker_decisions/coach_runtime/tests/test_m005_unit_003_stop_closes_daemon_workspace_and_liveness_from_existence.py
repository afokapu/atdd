# URN: test:mediate-worker-decisions:coach-runtime:M005-UNIT-003-stop-closes-daemon-workspace-and-liveness-from-existence
# Acceptance: acc:mediate-worker-decisions:M005-UNIT-003-stop-closes-daemon-workspace-and-liveness-from-existence
# WMBT: wmbt:mediate-worker-decisions:M005
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""M005-UNIT-003 — stop closes the daemon's cmux surface; liveness = it exists.

With the daemon now living inside a cmux surface (#1007), the lifecycle is
workspace-based: ``cmux close-workspace`` over the daemon's OWN workspace ref reads
the cmux ``list-workspaces`` output for liveness. ``CmuxWorkspaceCloser`` closes the
recorded daemon workspace; ``CmuxWorkspaceLiveness`` reports a daemon running iff its
workspace ref still appears in ``list-workspaces``.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
    CmuxWorkspaceCloser,
    CmuxWorkspaceLiveness,
)


def test_closer_closes_the_recorded_daemon_workspace():
    calls = []

    def _runner(*args):
        calls.append(list(args))
        return ""

    CmuxWorkspaceCloser(runner=_runner).close("workspace:55")

    assert calls == [["close-workspace", "--workspace", "workspace:55"]]


def test_liveness_reads_workspace_existence_from_list_workspaces():
    listing = (
        "* workspace:1  ATDD COACH  [selected]\n"
        "  workspace:55  atdd-coach-daemon-ws-target\n"
        "  workspace:6  TOURNAMENT\n"
    )

    probe = CmuxWorkspaceLiveness(runner=lambda *args: listing)

    assert probe.is_alive("workspace:55") is True  # surface still present
    assert probe.is_alive("workspace:999") is False  # surface gone → stale
    assert probe.is_alive("") is False  # never-launched record
