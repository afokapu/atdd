# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C013-UNIT-003-a-raised-exception-is-still-a-failure
# Acceptance: acc:govern-lifecycle:C013-UNIT-003-a-raised-exception-is-still-a-failure
# WMBT: wmbt:govern-lifecycle:C013
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C013-UNIT-003 — E046 survives the new verdict intact.

``run_checks`` converts any exception a check raises into a FAILING result. That
is correct and load-bearing, and it is the single most attractive thing to break
while adding this verdict: a crashed check *did* fail to observe, so routing it
to ``COULD_NOT_CHECK`` reads plausible.

It is wrong. A raised exception is a diagnosable fault with a traceback and a
cause — a missing tool, a timeout, a bug. "Could not check" is the honest,
*non-raising* branch: the check ran to completion and had nothing to report on.
Collapsing them loses the distinction this WMBT exists to create, and it would
quietly reclassify every existing fail-closed conversion in the tree.

Both still block, so this test cannot be satisfied by looking at ``proceed``. It
asserts on the verdict itself, which is the only place the difference lives.

RED state: ``atdd.coach.gate.decision`` declares no ``GateVerdict``.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from atdd.coach.gate.decision import (
    GateContext,
    GateVerdict,
    evaluate_gate,
    run_checks,
)

pytestmark = [pytest.mark.platform]


@dataclass(frozen=True)
class RaisingCheck:
    """A check whose ``run`` raises — the E046 shape, parameterised by cause."""

    exc: BaseException
    gate_id: str = "GT-EXPLODES"
    rule_id: str = "repo.govern-lifecycle.c013"

    def run(self, ctx: GateContext):
        raise self.exc


@pytest.fixture()
def ctx(tmp_path: Path) -> GateContext:
    return GateContext(issue_number=1719, from_phase="PLANNED", to_phase="RED", worktree=tmp_path)


#: The three causes E046 names: a generic error, a missing tool, a timeout.
_CAUSES = [
    pytest.param(RuntimeError("boom"), id="generic-error"),
    pytest.param(FileNotFoundError("no such tool: atdd-nonexistent"), id="missing-tool"),
    pytest.param(subprocess.TimeoutExpired(cmd="sleep", timeout=0.01), id="timeout"),
]


@pytest.mark.parametrize("exc", _CAUSES)
def test_a_raised_exception_becomes_a_failure_not_an_unobservable_result(exc, ctx):
    """E046's conversion target is FAIL, and the new verdict must not steal it."""
    results = run_checks([RaisingCheck(exc)], ctx)

    assert len(results) == 1
    result = results[0]
    assert result.verdict is GateVerdict.FAIL, (
        f"a raised {type(exc).__name__} was reclassified as {result.verdict}; a crash is a "
        f"diagnosable fault, not an honest inability to observe"
    )
    assert result.verdict is not GateVerdict.COULD_NOT_CHECK
    assert result.passed is False


@pytest.mark.parametrize("exc", _CAUSES)
def test_the_converted_failure_still_blocks_and_still_lands_in_failures(exc, ctx):
    """The fail-closed guarantee itself, unchanged: refuse, and say why."""
    outcome = evaluate_gate(run_checks([RaisingCheck(exc)], ctx))

    assert outcome.proceed is False
    assert len(outcome.failures) == 1, "E046's result must stay in the failures bucket"
    assert outcome.unobservable == (), "an exception must not be reported as unobservable"
    assert outcome.failures[0].gate_id == "GT-EXPLODES"
    assert outcome.failures[0].rule_id == "repo.govern-lifecycle.c013"
    assert outcome.failures[0].message, "the converted failure must carry the cause"


def test_no_exception_escapes_run_checks(ctx):
    """Whatever the cause, the gate returns a verdict rather than propagating."""
    results = run_checks([RaisingCheck(RuntimeError("boom")), RaisingCheck(KeyError("k"))], ctx)

    assert len(results) == 2
    assert all(r.verdict is GateVerdict.FAIL for r in results)
