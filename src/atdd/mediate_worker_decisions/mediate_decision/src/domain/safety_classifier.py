"""Pure safety classifier: a decision request -> SAFE | HUMAN_REQUIRED (no I/O).

Examines the question and every option label (natural language). A single
dangerous option taints the whole request — the human decides, not the coach
(WMBT C002). Danger is detected by the shared ``match_danger`` fast-path, whose
pattern set now covers the full destructive git/fs/db surface (reset --hard,
clean -fd, branch -D, rebase, restore, DELETE FROM, truncate, dd, mkfs,
chmod -R, ...) — not only push/merge (#1014).

This gate stays SAFE-by-default for prose: option labels are natural language
(Yes/No/"add a unit test"), so only an explicit danger match escalates. The
escalate-by-default allowlist applies to the shell-command gate
(``tool_input_safety``), not to decision-option prose.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from atdd.mediate_worker_decisions.mediate_decision.src.domain.danger_rules import (
    match_danger,
)

SAFE = "safe"
HUMAN_REQUIRED = "human_required"


@dataclass(frozen=True)
class SafetyClass:
    classification: str  # SAFE | HUMAN_REQUIRED
    matched_rule: Optional[str] = None

    @property
    def is_safe(self) -> bool:
        return self.classification == SAFE


def classify(question: str, option_labels: Iterable[str]) -> SafetyClass:
    haystack = " \n ".join([question, *option_labels])
    matched = match_danger(haystack)
    if matched is None:
        return SafetyClass(SAFE)
    return SafetyClass(HUMAN_REQUIRED, matched_rule=matched)
