# URN: test:spawn-agents:spawn-time-non-interactive-convention:E014-UNIT-002-bash-auto-approve-fix-hint-references-allowlist
# Acceptance: acc:spawn-agents:E014-UNIT-002-bash-auto-approve-fix-hint-references-allowlist
"""E014-UNIT-002 — build_rule().fix_hint references spawn-time allowlist and atdd agent escalate.

RED: fix_hint currently says 'operator review required' with no reference to the
spawn-time allowlist or atdd agent escalate.
GREEN: fix_hint mentions 'acceptEdits' (or 'allowedTools') and 'atdd agent escalate'.
"""
import pytest
from atdd.coach.observer_rules.bash_auto_approve import build_rule


def test_fix_hint_references_accept_edits_or_allowed_tools():
    rule = build_rule()
    fix_hint = getattr(rule, "fix_hint", None) or ""
    assert "acceptEdits" in fix_hint or "allowedTools" in fix_hint, (
        f"build_rule().fix_hint does not reference 'acceptEdits' or 'allowedTools'. "
        f"E014: fix_hint must explain the spawn-time allowlist. Got: {fix_hint!r}"
    )


def test_fix_hint_references_atdd_agent_escalate():
    rule = build_rule()
    fix_hint = getattr(rule, "fix_hint", None) or ""
    assert "atdd agent escalate" in fix_hint, (
        f"build_rule().fix_hint does not reference 'atdd agent escalate'. "
        f"E014: fix_hint must direct deny-pattern bashes to the structured escalation channel. "
        f"Got: {fix_hint!r}"
    )


def test_fix_hint_does_not_reference_multiplexer():
    rule = build_rule()
    fix_hint = getattr(rule, "fix_hint", None) or ""
    assert "multiplexer" not in fix_hint.lower(), (
        f"build_rule().fix_hint still references 'multiplexer' — stale modal-typing path. "
        f"E014: remove multiplexer references from fix_hint. Got: {fix_hint!r}"
    )
