"""OrchestratorConfig — the frozen knobs of the persistent supervisor loop.

Pure domain: terminal phases (the loop stops when the work item reaches one),
the stall threshold (consecutive done-signal-absent polls in one phase before the
loop loud-logs and exits, WMBT M006), and the poll interval the injected clock
sleeps for. No I/O, no imports from other layers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet

# The lifecycle's absorbing states: once a work item reaches one the supervisor
# has nothing left to drive (COMPLETE = done; BLOCKED = parked for a human).
DEFAULT_TERMINAL_PHASES: FrozenSet[str] = frozenset({"COMPLETE", "BLOCKED"})


@dataclass(frozen=True)
class OrchestratorConfig:
    """Loop knobs: terminal phases, stall threshold, and poll interval."""

    terminal_phases: FrozenSet[str] = field(default=DEFAULT_TERMINAL_PHASES)
    stall_threshold: int = 3
    poll_interval_s: float = 2.0

    def is_terminal(self, phase: str) -> bool:
        """True when ``phase`` is an absorbing lifecycle state (nothing to drive)."""
        return phase in self.terminal_phases
