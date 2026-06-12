"""ManagerRegistryAttachProbe — the real daemon-attach reader (WMBT M006).

The integration adapter behind ``DaemonAttachProbe``: it reads the coach-runtime
``ManagerRegistry`` (one ``manager.json`` per watched workspace) and reports whether
a live daemon is attached to a worker's workspace. A registry record IS how an
attached daemon is represented — full daemon-process liveness is a coach-runtime
concern (M004/M005); the gate only needs the attach signal to decide HANDLED vs
UNMEDIATED.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
    ManagerRegistry,
)
from atdd.mediate_worker_decisions.verify_producer_gate.src.application.ports import (
    AttachState,
)


class ManagerRegistryAttachProbe:
    """Reports daemon-attach state for a workspace from the coach-runtime registry.

    Structurally a ``DaemonAttachProbe`` (the application port) — mirrors the sibling
    ``CmuxHookProbe`` convention of implementing the port without inheriting it.
    """

    def __init__(self, registry: ManagerRegistry) -> None:
        self._registry = registry

    def evaluate(self, workspace: str) -> AttachState:
        daemon = self._registry.load(workspace)
        if daemon is None:
            return AttachState(
                attached=False, daemon_ref="", reason="no manager record for workspace"
            )
        return AttachState(
            attached=True,
            daemon_ref=daemon.daemon_workspace,
            reason="manager record present",
        )
