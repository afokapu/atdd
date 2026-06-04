"""DaemonConfig — frozen value object holding the daemon's runtime knobs.

Pure data: poll cadence, the single-instance lock path, and the two durable
ledger paths (escalations + verdicts) used for the human-escalation audit trail
and for answered-set re-hydration on restart.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DaemonConfig:
    workspace_id: str
    lock_path: Path
    escalations_path: Path
    verdicts_path: Path
    poll_interval_s: float = 2.0
