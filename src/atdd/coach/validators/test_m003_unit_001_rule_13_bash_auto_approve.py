# URN: component:observe-and-correct:observer-runtime-and-rules:test_m003_unit_001_rule_13_bash_auto_approve:backend:domain
# Runtime: python
# Purpose: Reverse-coherence binding for coach.observer.bash-auto-approve (rule 13).

"""Validator wrapper for observer rule 13 (issue #513).

Binds ``coach.observer.bash-auto-approve`` and asserts the absorption-pattern
parity between the rule and ``babysit.classify_prompt`` per spec §0.2.

The detailed parity unit tests live next to the rule module at
``src/atdd/coach/commands/tests/test_m003_unit_001_rule_13_bash_auto_approve.py``;
this validator is the ``validator:`` back-reference required by
``test_rule_validator_binding.py`` (issue #399).
"""
from __future__ import annotations

import pytest

from atdd.coach.commands import babysit, observer
from atdd.coach.observer_rules import bash_auto_approve
from atdd.coach.utils.rule_binding import bind_rule


_RULE = bind_rule("coach.observer.bash-auto-approve")


pytestmark = [pytest.mark.coach]


def _screen_with_bash(cmd: str) -> str:
    return f"... earlier output ...\nBash({cmd})\nDo you want to proceed?\n❯ 1. Yes\n"


def test_rule_13_parity_with_classify_prompt():
    """Rule 13 fires for escalation cases at parity with babysit.classify_prompt."""
    assert _RULE.rule_id == "coach.observer.bash-auto-approve"

    # Auto-approve case: known-safe bash → predicate False (no escalation).
    safe_screen = _screen_with_bash("git status")
    assert babysit.classify_prompt(safe_screen).action == "auto_approve"
    assert bash_auto_approve.predicate(
        observer.ObservedInput(
            agent_id="agent-A",
            log_lines=tuple(safe_screen.splitlines()),
        )
    ) is False

    # Escalation case: deny-pattern bash → predicate True.
    deny_screen = _screen_with_bash("rm -rf /tmp/x")
    assert babysit.classify_prompt(deny_screen).action == "escalate"
    assert bash_auto_approve.predicate(
        observer.ObservedInput(
            agent_id="agent-A",
            log_lines=tuple(deny_screen.splitlines()),
        )
    ) is True

    # Idle case: no prompt marker → predicate False.
    idle_screen = "just output\n"
    assert babysit.classify_prompt(idle_screen).action == "idle"
    assert bash_auto_approve.predicate(
        observer.ObservedInput(
            agent_id="agent-A",
            log_lines=tuple(idle_screen.splitlines()),
        )
    ) is False

    # Absorption: rule 13 reuses babysit's helpers verbatim per spec §0.2.
    assert bash_auto_approve.classify_prompt is babysit.classify_prompt
    assert bash_auto_approve._load_bash_patterns is babysit._load_bash_patterns
    assert bash_auto_approve.BashPattern is babysit.BashPattern
