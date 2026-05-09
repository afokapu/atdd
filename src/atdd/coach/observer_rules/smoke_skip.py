# URN: component:observe-and-correct:observer-runtime-and-rules:smoke_skip:backend:application
# Runtime: python
# Purpose: Observer rule 16 — flag GREEN→REFACTOR phase transitions without an intervening SMOKE (absorbs babysit.detect_violation SMOKE-skip clause).

"""Observer rule 16 — ``coach.observer.smoke-skip`` (spec §6.4 / §8.3).

Absorbs the ``--status REFACTOR`` clause of ``babysit.detect_violation``
verbatim per spec §0.2. Only the SMOKE-skip variant of
``detect_violation`` is owned by this rule; the ``.atdd/`` hand-edit
violation is a separate observer rule.
"""
from __future__ import annotations

from atdd.coach.commands import observer
from atdd.coach.commands.babysit import detect_violation


_RULE_ID = "coach.observer.smoke-skip"
_CORRECTION_TEXT = (
    "Phase transition GREEN → REFACTOR detected without an intervening SMOKE. "
    "Run SMOKE phase tests against real infrastructure before transitioning to REFACTOR. "
    "See atdd-coach-spec-v9.md §6.4."
)


def predicate(ctx: observer.ObservedInput) -> bool:
    """True when ``babysit.detect_violation`` flags the SMOKE-skip variant."""
    if not ctx.log_lines:
        return False
    screen = "\n".join(ctx.log_lines)
    decision = detect_violation(screen)
    if decision is None:
        return False
    return decision.matched == "SMOKE skip"


def build_rule() -> observer.ObserverRule:
    return observer.ObserverRule(
        rule_id=_RULE_ID,
        predicate=predicate,
        correction_text=_CORRECTION_TEXT,
        injection_method="cli-return",
        severity=4,
        disposition="strict",
    )


__all__ = [
    "build_rule",
    "detect_violation",
    "predicate",
]
