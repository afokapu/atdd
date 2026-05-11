# URN: component:observe-and-correct:observer-runtime-and-rules:bash_auto_approve:backend:application
# Runtime: python
# Purpose: Observer rule 13 — auto-approve known-safe bash prompts; escalate deny-pattern prompts (absorbs babysit.classify_prompt).

"""Observer rule 13 — ``coach.observer.bash-auto-approve`` (spec §8.3).

Absorbs ``babysit.classify_prompt`` verbatim per spec §0.2. The classifier
reads ``orchestration.convention.yaml::babysit.bash_auto_approve_patterns``
and ``bash_deny_patterns`` via ``babysit._load_bash_patterns`` /
``babysit.BashPattern`` — the patterns YAML is unchanged.

Predicate semantics:

  * ``classify_prompt`` returns ``action == "auto_approve"`` → predicate
    returns ``False`` (no operator-visible correction needed; the
    multiplexer separately sends ``"1\\n"`` to accept).
  * ``classify_prompt`` returns ``action == "escalate"`` → predicate
    returns ``True`` so the observer writes an escalation correction.
  * ``classify_prompt`` returns ``action == "idle"`` → predicate returns
    ``False``.
"""
from __future__ import annotations

from atdd.coach.commands import observer
from atdd.coach.commands._archived.babysit import (
    BashPattern,
    _load_bash_patterns,
    classify_prompt,
)


_RULE_ID = "coach.observer.bash-auto-approve"
_CORRECTION_TEXT = (
    "Bash prompt did not match an auto-approve pattern — operator review required. "
    "See orchestration.convention.yaml::babysit.bash_auto_approve_patterns."
)


def predicate(ctx: observer.ObservedInput) -> bool:
    """Fire when the visible screen contains a non-auto-approvable prompt."""
    if not ctx.log_lines:
        return False
    screen = "\n".join(ctx.log_lines)
    decision = classify_prompt(screen)
    return decision.action == "escalate"


def build_rule() -> observer.ObserverRule:
    return observer.ObserverRule(
        rule_id=_RULE_ID,
        predicate=predicate,
        correction_text=_CORRECTION_TEXT,
        injection_method="cli-return",
        severity=3,
        disposition="advisory",
    )


__all__ = [
    "BashPattern",
    "_load_bash_patterns",
    "build_rule",
    "classify_prompt",
    "predicate",
]
