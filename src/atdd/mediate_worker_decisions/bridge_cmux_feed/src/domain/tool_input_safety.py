"""Pure safety gate for a permission's tool_input (WMBT C003).

A tool_input is a shell command the worker asked permission to run. The gate is
an **allowlist**, not a denylist: ``auto`` ONLY for a known read-only command,
``human_required`` for every danger-pattern match AND every unrecognized command
(escalate-by-default). A denylist whose default is ``auto`` silently
auto-approved ``git reset --hard``, ``git clean -fd`` and ``git branch -D`` in a
live stress test (#1014) — the allowlist closes that long-tail hole. This runs
BEFORE the coach is ever consulted, so an unrecognized mutation is never
auto-replied.

``is_dangerous`` is the prose companion: for confirm-block prompts / option
labels (natural language, not a shell command) the danger is only an explicit
danger-pattern match — these must NOT be forced through the command allowlist,
which would escalate every benign confirm.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.mediate_decision.src.domain.danger_rules import (
    AUTO,
    HUMAN_REQUIRED,
    classify_command,
    match_danger,
)

__all__ = ["AUTO", "HUMAN_REQUIRED", "classify", "is_dangerous"]


def classify(tool_input: str) -> str:
    """Return ``auto`` for a recognized read-only command, else ``human_required``."""
    return classify_command(tool_input or "")


def is_dangerous(text: str) -> bool:
    """True iff ``text`` (prose) matches an explicit danger pattern (WMBT C005)."""
    return match_danger(text or "") is not None
