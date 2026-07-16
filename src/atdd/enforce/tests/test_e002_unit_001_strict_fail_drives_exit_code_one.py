# URN: test:enforce-conventions-ci:E002-UNIT-001-strict-fail-drives-exit-code-one
# Acceptance: acc:enforce-conventions-ci:E002-UNIT-001-strict-fail-drives-exit-code-one
# WMBT: wmbt:enforce-conventions-ci:E002
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:enforce-conventions-ci:E002-UNIT-001-strict-fail-drives-exit-code-one.

PINS the aggregation a BLOCKING gate rests on (it does not rebuild it — the
plumbing already works). An EnforceResult carrying at least one failed rule
reports ``passed=False`` / ``exit_code=1``; an all-passing result reports 0; and
verdicts that merely did not RUN (skip / exempt / unrunnable) never by themselves
drive a non-zero exit.

That last clause is the subtle one: were an ``unrunnable`` rule to count as a
failure, the gate would red on the toolkit's known provider gap; were a ``fail``
to count as a non-run, the gate would go green on a failing repository. A silent
false green is the one failure mode a required check cannot tolerate.
"""
from __future__ import annotations

import pytest

from atdd.enforce.runner import EnforceResult, RuleVerdict

WS = "atdd.workspace.python-pytest"


def _result(*verdicts: RuleVerdict) -> EnforceResult:
    return EnforceResult(verdicts=list(verdicts), report="")


def test_a_failed_strict_verdict_drives_exit_code_one() -> None:
    result = _result(
        RuleVerdict("coder.logging.print", WS, "pass"),
        RuleVerdict("coder.security.sql-injection", WS, "fail", raw_violation_count=1),
    )

    assert result.passed is False
    assert result.exit_code == 1


def test_an_all_passing_result_drives_exit_code_zero() -> None:
    result = _result(
        RuleVerdict("coder.logging.print", WS, "pass"),
        RuleVerdict("coder.boundaries.http-client", WS, "pass"),
    )

    assert result.passed is True
    assert result.exit_code == 0


@pytest.mark.parametrize("status", ["skip", "exempt", "unrunnable"])
def test_a_verdict_that_did_not_run_never_by_itself_fails_the_build(status: str) -> None:
    result = _result(RuleVerdict("coder.dead-code.reachability", WS, status))

    assert result.passed is True
    assert result.exit_code == 0


def test_one_failure_among_many_non_failures_is_enough_to_fail() -> None:
    # The realistic shape: one real regression buried among skipped/exempt/unrunnable
    # rules must still red the build.
    result = _result(
        RuleVerdict("a.b.skipped", WS, "skip"),
        RuleVerdict("a.b.exempt", WS, "exempt"),
        RuleVerdict("a.b.unrunnable", WS, "unrunnable"),
        RuleVerdict("a.b.passing", WS, "pass"),
        RuleVerdict("a.b.failing", WS, "fail", raw_violation_count=1),
    )

    assert result.passed is False
    assert result.exit_code == 1
