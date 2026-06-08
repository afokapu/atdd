# URN: test:mediate-worker-decisions:coach-runtime:M005-UNIT-002-start-launches-daemon-as-headless-cmux-surface
# Acceptance: acc:mediate-worker-decisions:M005-UNIT-002-start-launches-daemon-as-headless-cmux-surface
# WMBT: wmbt:mediate-worker-decisions:M005
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""M005-UNIT-002 — start launches the daemon INSIDE a headless cmux surface.

The #1007 fix: cmux rejects orphaned/detached processes (a ``subprocess.Popen``
daemon broken-pipes on every ``cmux rpc``), so ``atdd coach start`` must launch the
feed_daemon as a ``cmux new-workspace --focus false --command`` surface — a
socket-recognized process — and record the daemon's OWN cmux workspace ref (distinct
from the watched target workspace), NOT a detached subprocess pid.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.coach_runtime.composition import build_coach_runtime
from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
    CmuxSurfaceDaemonLauncher,
    ManagerRegistry,
)
from atdd.mediate_worker_decisions.coach_runtime.tests._helpers import (
    FakeLiveness,
    RecordingCloser,
    StubGate,
)


class _RecordingRunner:
    """Captures the cmux argv and returns the daemon's new workspace ref."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(list(args))
        return "workspace:314"


def test_start_launches_daemon_as_headless_cmux_surface(tmp_path):
    root = tmp_path / "coach-runtime"
    runner = _RecordingRunner()
    runtime = build_coach_runtime(
        registry=ManagerRegistry(root),
        spawner=CmuxSurfaceDaemonLauncher(cwd=str(tmp_path), runner=runner),
        liveness=FakeLiveness(),  # no existing daemon → not consulted on first start
        closer=RecordingCloser(),
        gate=StubGate(),
    )

    daemon = runtime.start(
        "ws-target",
        lock_path=str(tmp_path / "feed.lock"),
        escalations_path=str(tmp_path / "escalations.jsonl"),
        verdicts_path=str(tmp_path / "verdicts.jsonl"),
    )

    # Launched as a headless cmux surface (new-workspace --focus false --command),
    # NOT a detached subprocess.
    assert len(runner.calls) == 1
    argv = runner.calls[0]
    assert argv[0] == "new-workspace"
    assert argv[argv.index("--focus") + 1] == "false"
    command = argv[argv.index("--command") + 1]
    assert "--workspace" in command and "ws-target" in command  # daemon argv inside

    # The persisted record names the daemon's OWN cmux workspace, distinct from the
    # watched target workspace.
    assert daemon.daemon_workspace == "workspace:314"
    assert daemon.daemon_workspace != "ws-target"
    reloaded = ManagerRegistry(root).load("ws-target")
    assert reloaded is not None
    assert reloaded.daemon_workspace == "workspace:314"
    assert reloaded.workspace_id == "ws-target"
