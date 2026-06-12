"""MediationStatus — HANDLED requires a confirmed daemon attach (WMBT M006).

A published gated decision is only ``HANDLED`` when a live daemon is confirmed
attached to the worker's workspace. A daemon-attach failure yields
``UNMEDIATED`` — never a silent HANDLED for an unmediated worker (#1084/A1).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Verdict causes the gate records.
CAUSE_MEDIATED = "mediated"
CAUSE_NO_ATTACHED_DAEMON = "no_attached_daemon"


@dataclass(frozen=True)
class MediationStatus:
    """The gate's verdict on whether a published decision was actually mediated."""

    handled: bool
    cause: str
    daemon_ref: Optional[str]
