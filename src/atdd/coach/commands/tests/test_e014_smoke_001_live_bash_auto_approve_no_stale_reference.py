# URN: test:spawn-agents:spawn-time-non-interactive-convention:E014-SMOKE-001-live-bash-auto-approve-no-stale-modal-reference
# Acceptance: acc:spawn-agents:E014-SMOKE-001-live-bash-auto-approve-no-stale-modal-reference
# WMBT: wmbt:spawn-agents:E014
# Phase: SMOKE
# Layer: smoke
# Runtime: python
# Assertion: behavioral
"""E014-SMOKE-001 — the deployed bash_auto_approve.py has no stale modal-typing
reference and build_rule() returns a rule whose fix_hint references acceptEdits
and atdd agent escalate.

SMOKE: reads the real source file and calls the real build_rule().
"""
from __future__ import annotations

import inspect

import pytest


@pytest.mark.smoke
def test_live_bash_auto_approve_no_stale_modal_reference():
    from atdd.coach.observer_rules import bash_auto_approve

    source = inspect.getsource(bash_auto_approve)
    assert "multiplexer separately sends" not in source, (
        "E014-SMOKE-001: stale 'multiplexer separately sends' text found in "
        "live bash_auto_approve.py source. E014 fix not applied."
    )


@pytest.mark.smoke
def test_live_bash_auto_approve_fix_hint_references_allowlist_and_escalate():
    from atdd.coach.observer_rules.bash_auto_approve import build_rule

    rule = build_rule()
    fix_hint = rule.fix_hint or ""
    assert "acceptEdits" in fix_hint or "allowedTools" in fix_hint, (
        f"E014-SMOKE-001: fix_hint must reference acceptEdits or allowedTools. Got: {fix_hint!r}"
    )
    assert "atdd agent escalate" in fix_hint, (
        f"E014-SMOKE-001: fix_hint must reference 'atdd agent escalate'. Got: {fix_hint!r}"
    )
