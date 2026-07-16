# URN: test:enforce-conventions-ci:E003-UNIT-001-baseline-holds-pre-existing-violations-flat
# Acceptance: acc:enforce-conventions-ci:E003-UNIT-001-baseline-holds-pre-existing-violations-flat
# WMBT: wmbt:enforce-conventions-ci:E003
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:enforce-conventions-ci:E003-UNIT-001-baseline-holds-pre-existing-violations-flat.

A rule failing at or below its recorded baseline is held FLAT — the aggregate
result passes (exit 0) so the blocking job stays green over known debt — yet the
held-flat rule is still NAMED in the report with its baselined count, so the debt
stays visible rather than being silently forgiven.
"""
from __future__ import annotations

from atdd.enforce.ratchet import BASELINED, apply_ratchet
from atdd.enforce.runner import EnforceResult, RuleVerdict

WS = "atdd.workspace.python-pytest"


def _fail(rule_id: str, count: int) -> RuleVerdict:
    return RuleVerdict(
        rule_id,
        WS,
        "fail",
        raw_violation_count=count,
        locations=[f"{rule_id}.py:{i}:0" for i in range(count)],
        detail=f"{count} violation(s)",
    )


def _result(*verdicts: RuleVerdict) -> EnforceResult:
    return EnforceResult(verdicts=list(verdicts), report="")


def test_rule_failing_at_exactly_its_baseline_is_held_flat() -> None:
    result = _result(_fail("coder.refactor.complexity-nesting", 278))

    ratcheted = apply_ratchet(result, {"coder.refactor.complexity-nesting": 278})

    (verdict,) = ratcheted.verdicts
    assert verdict.status == BASELINED
    assert verdict.failed is False
    # The aggregate passes: the blocking job is green over the known debt.
    assert ratcheted.passed is True
    assert ratcheted.exit_code == 0


def test_rule_failing_below_its_baseline_is_held_flat_so_paying_debt_never_breaks_the_build() -> None:
    # 300 violations against a baseline of 308 — eight were fixed.
    result = _result(_fail("coder.logging.coach-silent-swallow", 300))

    ratcheted = apply_ratchet(result, {"coder.logging.coach-silent-swallow": 308})

    (verdict,) = ratcheted.verdicts
    assert verdict.status == BASELINED
    assert ratcheted.exit_code == 0


def test_held_flat_debt_is_still_named_in_the_report_not_silently_forgiven() -> None:
    result = _result(_fail("coder.dead-code.reachability", 319))

    ratcheted = apply_ratchet(result, {"coder.dead-code.reachability": 319})

    report = ratcheted.report
    # The rule is NAMED, with both its current count and the baseline it is held at.
    assert "coder.dead-code.reachability" in report
    assert "319" in report
    assert BASELINED.upper() in report
    # ...and the summary says the debt is held, not that the repo is clean.
    assert "held flat" in report
    assert "PASS" in report


def test_a_genuinely_passing_rule_is_untouched_by_the_ratchet() -> None:
    passing = RuleVerdict("coder.boundaries.http-client", WS, "pass")
    result = _result(passing, _fail("coder.security.sql-injection", 1))

    ratcheted = apply_ratchet(result, {"coder.security.sql-injection": 1})

    by_id = {v.rule_id: v for v in ratcheted.verdicts}
    assert by_id["coder.boundaries.http-client"].status == "pass"
    assert by_id["coder.security.sql-injection"].status == BASELINED
    assert ratcheted.exit_code == 0
