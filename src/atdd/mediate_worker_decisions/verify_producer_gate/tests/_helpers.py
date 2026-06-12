"""Shared test fakes for verify-producer-gate RED tests (#1076)."""
from __future__ import annotations

from atdd.mediate_worker_decisions.verify_producer_gate.src.application.ports import (
    AttachState,
    DaemonAttachProbe,
)

# The post-#1062 scoped Bash freedom-layer allow-list (image of the comma-delimited
# `Bash(<pattern>)` patterns spawned workers carry, #1062 E031/E032). pytest is
# pre-authorized; git push is not.
FREEDOM_LAYER_BASH_ALLOW = (
    "pytest:*",
    "atdd validate:*",
    "atdd repo:*",
    "grep:*",
    "rg:*",
    "ls:*",
)


class StubAttachProbe(DaemonAttachProbe):
    """A DaemonAttachProbe that reports a fixed attach state for any workspace."""

    def __init__(self, *, attached: bool, daemon_ref: str = "", reason: str = ""):
        self._state = AttachState(
            attached=attached, daemon_ref=daemon_ref, reason=reason
        )
        self.calls: list[str] = []

    def evaluate(self, workspace: str) -> AttachState:
        self.calls.append(workspace)
        return self._state
