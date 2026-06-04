"""DaemonConfig — frozen value object holding the daemon's runtime knobs.

Pure data: poll cadence, the single-instance lock path, the two durable ledger
paths (escalations + verdicts) used for the human-escalation audit trail and for
answered-set re-hydration on restart, and the pluggable decider selection
(``coach_provider``/``coach_model``). The decider is agnostic by construction —
``coach_provider`` defaults to ``claude`` (the only implementation today) and
``coach_model`` optionally pins a model.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class DaemonConfig:
    workspace_id: str
    lock_path: Path
    escalations_path: Path
    verdicts_path: Path
    poll_interval_s: float = 2.0
    coach_provider: str = "claude"
    coach_model: Optional[str] = None
