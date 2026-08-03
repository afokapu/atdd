# URN: test:verify-enforcement:M001-UNIT-001-classification-separates-enforced-from-reported
# Acceptance: acc:verify-enforcement:M001-UNIT-001-classification-separates-enforced-from-reported
# WMBT: wmbt:verify-enforcement:M001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:verify-enforcement:M001-UNIT-001-classification-separates-enforced-from-reported.

The per-rule classification is total and honest: a bound gating rule counts as
ENFORCED only under a blocking Path B; a bound advisory or documentation-only
rule is REPORTED; a bound gating rule under an advisory Path B is REPORTED; an
unbound rule is UNBOUND. So the bound set is demonstrably not the enforced set.
"""
from __future__ import annotations

from atdd.enforce.coverage_report import build_coverage_report

# Four dispositions across the treatment vocabulary, plus a gating node the lock
# does NOT bind — enough to separate all three enforcement statuses.
DECLARED = {
    "acme.rule.strict": "strict",
    "acme.rule.suppress": "suppress-and-clean",
    "acme.rule.advisory": "advisory",
    "acme.rule.docs": "documentation-only",
    "acme.rule.unbound": "strict",
}
BOUND = {
    "acme.rule.strict",
    "acme.rule.suppress",
    "acme.rule.advisory",
    "acme.rule.docs",
}


def test_classification_separates_enforced_from_reported() -> None:
    # Under a BLOCKING Path B the bound GATING nodes gate CI...
    blocking = build_coverage_report(DECLARED, BOUND, path_b_blocking=True)
    assert blocking.enforced == ["acme.rule.strict", "acme.rule.suppress"]
    # ...while advisory and documentation-only carry no gating verdict: REPORTED only.
    assert blocking.reported == ["acme.rule.advisory", "acme.rule.docs"]
    assert blocking.unbound == ["acme.rule.unbound"]

    # Under the ADVISORY Path B that CI actually runs, NOTHING is enforced by the
    # extension path — every bound node is merely REPORTED.
    advisory = build_coverage_report(DECLARED, BOUND, path_b_blocking=False)
    assert advisory.enforced == []
    assert advisory.reported == sorted(BOUND)
    assert advisory.unbound == ["acme.rule.unbound"]

    # The coverage truth: the enforced set is a STRICT subset of the bound set.
    assert advisory.bound == sorted(BOUND)
    assert set(advisory.enforced) < set(advisory.bound)
