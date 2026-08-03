# URN: test:enforce-conventions-ci:E003-UNIT-002-new-violation-over-the-baseline-fails
# Acceptance: acc:enforce-conventions-ci:E003-UNIT-002-new-violation-over-the-baseline-fails
# WMBT: wmbt:enforce-conventions-ci:E003
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:enforce-conventions-ci:E003-UNIT-002-new-violation-over-the-baseline-fails.

The ratchet may only ever TIGHTEN. A rule climbing even one violation above its
baseline FAILS (naming the baseline, the current count and the excess), and a rule
carrying NO baseline entry is held to zero — so no new debt can be smuggled in
under the register.
"""
from __future__ import annotations

from atdd.enforce.ratchet import BASELINED, apply_ratchet
from atdd.enforce.runner import EnforceResult, RuleVerdict

WS = "atdd.workspace.python-pytest"


def _fail(rule_id: str, count: int) -> RuleVerdict:
    return RuleVerdict(
        rule_id, WS, "fail", raw_violation_count=count,
        locations=[f"{rule_id}.py:{i}:0" for i in range(count)],
        detail=f"{count} violation(s)",
    )


def _result(*verdicts: RuleVerdict) -> EnforceResult:
    return EnforceResult(verdicts=list(verdicts), report="")


def test_one_violation_above_the_baseline_still_fails() -> None:
    # Baseline 278, the branch introduces one more.
    result = _result(_fail("coder.refactor.complexity-nesting", 279))

    ratcheted = apply_ratchet(result, {"coder.refactor.complexity-nesting": 278})

    (verdict,) = ratcheted.verdicts
    assert verdict.failed is True
    assert ratcheted.passed is False
    assert ratcheted.exit_code == 1


def test_the_regression_names_the_baseline_the_current_count_and_the_excess() -> None:
    result = _result(_fail("coder.refactor.complexity-cyclomatic", 210))

    ratcheted = apply_ratchet(result, {"coder.refactor.complexity-cyclomatic": 207})

    (verdict,) = ratcheted.verdicts
    # Diagnosable: what it is now, what it was allowed, and by how much it regressed.
    assert "210" in verdict.detail
    assert "207" in verdict.detail
    assert "+3" in verdict.detail
    report = ratcheted.report
    assert "coder.refactor.complexity-cyclomatic" in report
    assert "REGRESSION" in report
    assert "FAIL" in report


def test_a_rule_with_no_baseline_entry_is_held_to_zero_and_fails() -> None:
    # coder.logging.print is CLEAN today, so it carries no entry in the register.
    # It must not be able to start failing for free.
    result = _result(_fail("coder.logging.print", 1))

    ratcheted = apply_ratchet(result, {"coder.dead-code.reachability": 319})

    (verdict,) = ratcheted.verdicts
    assert verdict.failed is True, "an unregistered rule must be held to a baseline of zero"
    assert "baseline 0" in verdict.detail
    assert ratcheted.exit_code == 1


def test_a_regression_fails_even_while_other_rules_are_held_flat() -> None:
    # The realistic CI shape: 22 rules sitting on their baseline, one regressed.
    result = _result(
        _fail("coder.dead-code.reachability", 319),      # at baseline -> held
        _fail("coder.refactor.quality-naming", 4),       # baseline 3   -> REGRESSION
    )

    ratcheted = apply_ratchet(
        result,
        {"coder.dead-code.reachability": 319, "coder.refactor.quality-naming": 3},
    )

    by_id = {v.rule_id: v for v in ratcheted.verdicts}
    assert by_id["coder.dead-code.reachability"].status == BASELINED
    assert by_id["coder.refactor.quality-naming"].failed is True
    # One regression is enough to fail the build — the held-flat debt does not mask it.
    assert ratcheted.exit_code == 1
