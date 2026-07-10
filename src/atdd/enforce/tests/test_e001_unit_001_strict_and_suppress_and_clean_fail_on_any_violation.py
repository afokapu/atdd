# URN: test:reconcile-dispositions:reconcile-dispositions:E001-UNIT-001-strict-and-suppress-and-clean-fail-on-any-violation
# Acceptance: acc:reconcile-dispositions:E001-UNIT-001-strict-and-suppress-and-clean-fail-on-any-violation
# WMBT: wmbt:reconcile-dispositions:E001
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""E001-UNIT-001 — a strict node and a suppress-and-clean node each fail when the
provider reports at least one violation."""
from __future__ import annotations

from atdd.enforce.conventions import RuleMetadata
from atdd.enforce.runner import _verdict_for_rule

_ONE_VIOLATION = [{"rule_id": "x", "file": "a.py", "line": 1, "col": 1}]


def _meta(disposition: str) -> RuleMetadata:
    return RuleMetadata(rule_id="x", severity=None, disposition=disposition)


def test_e001_unit_001_strict_and_suppress_and_clean_fail_on_any_violation():
    assert _verdict_for_rule(_meta("strict"), _ONE_VIOLATION) == "fail"
    assert _verdict_for_rule(_meta("suppress-and-clean"), _ONE_VIOLATION) == "fail"
    # No violation -> pass, regardless of treatment.
    assert _verdict_for_rule(_meta("strict"), []) == "pass"
