"""PhaseSnapshot — the read the supervisor gets back from the phase poller.

A pure value object: the work item's current ``phase`` and whether that phase's
``done_signal`` is present. The supervisor advances only when ``done_signal`` is
True (WMBT C010); the real shape of the done-signal (e.g. a ``done.json``) lives
behind the injected poller and is the provider's concern.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhaseSnapshot:
    """The work item's current phase and the presence of its done-signal."""

    phase: str
    done_signal: bool
