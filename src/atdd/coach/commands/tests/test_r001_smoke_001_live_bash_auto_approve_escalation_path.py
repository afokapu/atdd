# URN: test:spawn-agents:spawn-time-non-interactive-convention:R001-SMOKE-001-live-bash-auto-approve-correction-references-escalate
# Acceptance: acc:spawn-agents:R001-SMOKE-001-live-bash-auto-approve-correction-references-escalate
# WMBT: wmbt:spawn-agents:R001
# Phase: SMOKE
# Layer: smoke
# Runtime: python
# Assertion: behavioral
"""R001-SMOKE-001 — the deployed bash_auto_approve.build_rule() returns a rule
whose correction_text contains 'atdd agent escalate'.

SMOKE: calls the real build_rule() from the deployed codebase.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
def test_live_bash_auto_approve_correction_references_agent_escalate():
    from atdd.coach.observer_rules.bash_auto_approve import build_rule

    rule = build_rule()
    assert "atdd agent escalate" in rule.correction_text, (
        f"R001-SMOKE-001: live build_rule().correction_text does not contain "
        f"'atdd agent escalate'. Deny-pattern escalation route not wired. "
        f"Got correction_text:\n{rule.correction_text}"
    )
    assert "send_key" not in rule.correction_text, (
        f"R001-SMOKE-001: correction_text must not reference send_key (modal typing). "
        f"Got: {rule.correction_text!r}"
    )
