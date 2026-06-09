"""Pure governance classifier: a decision -> SAFE | OPERATOR_RESERVED (no I/O).

The prose sibling of ``danger_rules``. Examines a decision's question + option
labels (and, via the runner, a document's leaf-block prompts/options) for
phase-transition sign-off / lifecycle-governance markers. A phase sign-off
("Approve → RED?", "advance to GREEN", "proceed to RED") is operator-reserved
and must ESCALATE, never be auto-answered (WMBT C007) — the same escalate
posture #1014 applied to danger, lifted to governance.

Conservative by design so the working auto-answer path does not regress: only an
explicit governance marker classifies operator_reserved — an ATDD phase token
reached by a transition arrow, or paired with an advance/approve verb on the
SAME line. Routine design-preference questions ("Which colour? Blue / Red")
stay SAFE even though "Red" is also a phase token, because no verb/arrow binds
to it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

SAFE = "safe"
OPERATOR_RESERVED = "operator_reserved"

# The ATDD lifecycle phase tokens an operator signs off on.
_PHASES = r"(?:INIT|PLANNED|RED|GREEN|SMOKE|REFACTOR|COMPLETE)"
# Verbs that, bound to a phase, denote a lifecycle sign-off. Deliberately narrow
# (no bare "go"/"move") to avoid false positives on routine prose.
_VERBS = r"(?:approve|advance|proceed|transition|sign[\s-]?off|promote)"

# A transition arrow into a phase is the strongest, least ambiguous signal.
_ARROWS = r"(?:->|→|➜|⇒|=>)"

_PATTERNS = (
    # "→ RED", "-> GREEN", "=> COMPLETE"
    re.compile(rf"{_ARROWS}\s*{_PHASES}\b", re.IGNORECASE),
    # verb ... phase on the same line: "Approve → RED", "advance to GREEN"
    re.compile(rf"\b{_VERBS}\b[^.\n]*\b{_PHASES}\b", re.IGNORECASE),
    # phase ... verb on the same line: "RED — approve?", "GREEN: promote"
    re.compile(rf"\b{_PHASES}\b[^.\n]*\b{_VERBS}\b", re.IGNORECASE),
)


def match_governance(text: str) -> Optional[str]:
    """Return the matched governance marker (the offending substring) or None."""
    for pattern in _PATTERNS:
        match = pattern.search(text or "")
        if match:
            return match.group(0).strip()
    return None


@dataclass(frozen=True)
class GovernanceClass:
    """SAFE vs OPERATOR_RESERVED with the matched marker (when reserved)."""

    classification: str  # SAFE | OPERATOR_RESERVED
    matched_marker: Optional[str] = None

    @property
    def is_operator_reserved(self) -> bool:
        return self.classification == OPERATOR_RESERVED


def classify_governance(question: str, option_labels: Iterable[str]) -> GovernanceClass:
    """Classify a decision from its question + option labels.

    Each option label is scanned on its own line so a phase token in one option
    cannot bind to a verb in another (preventing cross-option false positives).
    """
    parts = [question or "", *[label or "" for label in option_labels]]
    haystack = " \n ".join(parts)
    marker = match_governance(haystack)
    if marker is None:
        return GovernanceClass(SAFE)
    return GovernanceClass(OPERATOR_RESERVED, matched_marker=marker)
