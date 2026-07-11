# URN: test:verify-enforcement:M001-UNIT-002-report-names-enforced-and-reported-sets-distinctly
# Acceptance: acc:verify-enforcement:M001-UNIT-002-report-names-enforced-and-reported-sets-distinctly
# WMBT: wmbt:verify-enforcement:M001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:verify-enforcement:M001-UNIT-002-report-names-enforced-and-reported-sets-distinctly.

The rendered report is the coverage truth a reader can audit: it names the
ENFORCED set and the REPORTED-only set as distinct groups and lists each rule's
status, so which rules actually gate CI is stated, not inferred from the lock.
"""
from __future__ import annotations

from atdd.enforce.coverage_report import build_coverage_report, render_coverage_report

DECLARED = {
    "acme.rule.strict": "strict",
    "acme.rule.advisory": "advisory",
    "acme.rule.unbound": "strict",
}
BOUND = {"acme.rule.strict", "acme.rule.advisory"}


def test_report_names_enforced_and_reported_sets_distinctly() -> None:
    # The live shape: bound conventions under an advisory Path B.
    rendered = render_coverage_report(
        build_coverage_report(DECLARED, BOUND, path_b_blocking=False)
    )

    # The two groups are named as distinct groups...
    assert "ENFORCED" in rendered
    assert "REPORTED" in rendered
    # ...and the coverage truth is STATED, not left to the reader to infer.
    assert "the bound set is not the enforced set" in rendered

    # Every declared rule appears exactly once, with its status.
    for rule_id in DECLARED:
        assert rendered.count(rule_id) == 1


def test_report_states_coverage_is_honest_when_enforced_equals_bound() -> None:
    # When Path B blocks, every bound gating rule IS enforced — no gap to warn about.
    rendered = render_coverage_report(
        build_coverage_report(
            {"acme.rule.strict": "strict"}, {"acme.rule.strict"}, path_b_blocking=True
        )
    )
    assert "ENFORCED" in rendered
    assert "the bound set is not the enforced set" not in rendered
