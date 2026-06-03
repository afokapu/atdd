"""Pure safety gate for a permission's tool_input (WMBT C003).

Reuses the wagon's conservative danger-pattern matcher. A tool_input that
matches any danger pattern (git push, git merge, rm -rf, drop table, ...) is
``human_required``; anything else is ``auto``. This runs BEFORE the coach is
ever consulted, so a dangerous tool use is never auto-replied.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.mediate_decision.src.domain.danger_rules import (
    match_danger,
)

AUTO = "auto"
HUMAN_REQUIRED = "human_required"


def classify(tool_input: str) -> str:
    """Return ``human_required`` for a dangerous command, else ``auto``."""
    return HUMAN_REQUIRED if match_danger(tool_input) else AUTO
