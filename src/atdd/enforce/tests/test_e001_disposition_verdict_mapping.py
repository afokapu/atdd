"""RED tests for WMBT E001 — disposition-verdict-mapping (#1424).

Feature: feature:reconcile-dispositions:reconcile-dispositions

Fixes a LIVE BUG: ``runner._verdict_for_rule`` special-cases only ``advisory``,
so ``documentation-only`` falls through to fail-on-any-violation. The bound,
documentation-only convention ``tester.filename.urn`` FAILs the enforce verdict
today whenever its provider reports a record. The mapping must be TOTAL across
the treatment vocabulary: strict / suppress-and-clean fail on any violation;
advisory / documentation-only never fail.
"""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.conventions import RuleMetadata, rule_metadata
from atdd.enforce.runner import _verdict_for_rule, resolve_substrate_home

# A single synthetic raw v1.1 violation record (rule_id is joined by the caller).
_ONE_VIOLATION = [{"rule_id": "x", "file": "a.py", "line": 1, "col": 1}]

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _meta(disposition: str) -> RuleMetadata:
    return RuleMetadata(rule_id="x", severity=None, disposition=disposition)


# Acceptance: acc:reconcile-dispositions:E001-UNIT-001-strict-and-suppress-and-clean-fail-on-any-violation
def test_e001_unit_001_strict_and_suppress_and_clean_fail_on_any_violation():
    assert _verdict_for_rule(_meta("strict"), _ONE_VIOLATION) == "fail"
    assert _verdict_for_rule(_meta("suppress-and-clean"), _ONE_VIOLATION) == "fail"
    # No violation -> pass, regardless of treatment.
    assert _verdict_for_rule(_meta("strict"), []) == "pass"


# Acceptance: acc:reconcile-dispositions:E001-UNIT-002-advisory-and-documentation-only-never-fail
def test_e001_unit_002_advisory_and_documentation_only_never_fail():
    # advisory already passed; documentation-only is the regression this closes.
    assert _verdict_for_rule(_meta("advisory"), _ONE_VIOLATION) == "pass"
    assert _verdict_for_rule(_meta("documentation-only"), _ONE_VIOLATION) == "pass"


# Acceptance: acc:reconcile-dispositions:E001-SMOKE-001-enforce-does-not-fail-a-bound-documentation-only-rule
def test_e001_smoke_001_enforce_does_not_fail_a_bound_documentation_only_rule():
    """Against the committed vendored substrate, the bound documentation-only rule
    ``tester.filename.urn`` cannot produce a fail verdict — even with violations."""
    substrate_home = resolve_substrate_home(_REPO_ROOT)
    meta = rule_metadata(substrate_home, "tester.filename.urn")
    # The real vendored node declares documentation-only ...
    assert meta.disposition == "documentation-only"
    # ... so it never fails the build, even when the provider reports violations.
    assert _verdict_for_rule(meta, _ONE_VIOLATION) == "pass"
