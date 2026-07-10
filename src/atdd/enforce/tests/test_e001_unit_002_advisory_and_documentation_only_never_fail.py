# URN: test:reconcile-dispositions:E001-UNIT-002-advisory-and-documentation-only-never-fail
# Acceptance: acc:reconcile-dispositions:E001-UNIT-002-advisory-and-documentation-only-never-fail
# WMBT: wmbt:reconcile-dispositions:E001
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""E001-UNIT-002 — an advisory node and a documentation-only node each pass even
when the provider reports violations (closes the documentation-only regression)."""
from __future__ import annotations

from atdd.enforce.conventions import RuleMetadata
from atdd.enforce.runner import _verdict_for_rule

_ONE_VIOLATION = [{"rule_id": "x", "file": "a.py", "line": 1, "col": 1}]


def _meta(disposition: str) -> RuleMetadata:
    return RuleMetadata(rule_id="x", severity=None, disposition=disposition)


def test_e001_unit_002_advisory_and_documentation_only_never_fail():
    assert _verdict_for_rule(_meta("advisory"), _ONE_VIOLATION) == "pass"
    # documentation-only previously fell through to fail-on-any — now passes.
    assert _verdict_for_rule(_meta("documentation-only"), _ONE_VIOLATION) == "pass"
