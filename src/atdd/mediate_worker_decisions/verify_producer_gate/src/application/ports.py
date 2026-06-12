"""Ports for verify-producer-gate (application boundary, WMBT M006).

``DaemonAttachProbe`` reports whether a live daemon is attached/scoped to a
worker's workspace, so the gate derives a published decision's HANDLED status
from a confirmed attach rather than from the mere presence of a Feed item.
Injected so the gate stays unit-testable without a live daemon/cmux.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AttachState:
    """Whether a live daemon is attached to a workspace, and why not when it isn't."""

    attached: bool
    daemon_ref: str
    reason: str


class DaemonAttachProbe(Protocol):
    """Reports whether a live daemon is scoped/attached to ``workspace``."""

    def evaluate(self, workspace: str) -> AttachState: ...
