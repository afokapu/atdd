# URN: test:spawn-agents:spawn-time-non-interactive-convention:R001-UNIT-001-escalate-correction-references-atdd-agent-escalate
# URN: test:spawn-agents:spawn-time-non-interactive-convention:R001-UNIT-002-predicate-fires-on-deny-pattern-not-auto-approve
# Acceptance: acc:spawn-agents:R001-UNIT-001-escalate-correction-references-atdd-agent-escalate
# Acceptance: acc:spawn-agents:R001-UNIT-002-predicate-fires-on-deny-pattern-not-auto-approve
"""R001 — bash_auto_approve correction_text routes deny-pattern bashes to atdd agent escalate.

RED: correction_text is 'Bash prompt did not match an auto-approve pattern — operator review
required.' — no structured escalation path.
GREEN: correction_text contains 'atdd agent escalate'; fix_hint also references it.
"""
import pytest
from atdd.coach.observer_rules.bash_auto_approve import build_rule, predicate
from atdd.coach.commands.observer import ObservedInput


def test_correction_text_references_atdd_agent_escalate():
    rule = build_rule()
    assert "atdd agent escalate" in rule.correction_text, (
        f"build_rule().correction_text must reference 'atdd agent escalate' so the cli-return "
        f"channel instructs the agent to run the structured escalation. "
        f"R001: deny-pattern bashes route to atdd agent escalate. Got: {rule.correction_text!r}"
    )


def test_correction_text_does_not_reference_multiplexer_send():
    rule = build_rule()
    assert "multiplexer" not in rule.correction_text.lower(), (
        f"correction_text still references 'multiplexer'. "
        f"R001: corrections go through cli-return, not multiplexer.send. "
        f"Got: {rule.correction_text!r}"
    )


def test_predicate_fires_on_deny_pattern_bash():
    """predicate() returns True when screen shows a deny-pattern bash modal."""
    deny_screen = (
        "Bash(rm -rf /important/directory)\n"
        "Do you want to proceed?\n"
        "❯ 1. Yes\n"
        "  2. No\n"
    )
    ctx = ObservedInput(log_lines=deny_screen.splitlines(), agent_id="test-agent")
    result = predicate(ctx)
    assert result is True, (
        f"predicate() returned {result!r} for deny-pattern bash modal screen. "
        "R001: predicate must fire (True) so the escalation correction is emitted."
    )


def test_predicate_does_not_fire_on_idle_screen():
    """predicate() returns False when screen has no prompt markers (idle)."""
    idle_screen = "Working on it..."
    ctx = ObservedInput(log_lines=[idle_screen], agent_id="test-agent")
    result = predicate(ctx)
    assert result is False, (
        f"predicate() returned {result!r} for idle screen content (no prompt marker). "
        "R001: predicate must NOT fire for non-modal screens."
    )
