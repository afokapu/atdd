# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C013-UNIT-002-could-not-check-is-reported-apart-from-a-failure
# Acceptance: acc:govern-lifecycle:C013-UNIT-002-could-not-check-is-reported-apart-from-a-failure
# WMBT: wmbt:govern-lifecycle:C013
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C013-UNIT-002 — identical in effect, distinct in reporting.

``COULD_NOT_CHECK`` and ``FAIL`` both refuse the transition, so it would be
cheaper to merge them into one bucket and be done. That merge is exactly what
must not happen: the operator's next action differs completely between "your
code is broken" and "I could not look at your code", and a report that cannot
tell them apart sends the reader to the wrong remedy.

The last case here guards a caller, not the aggregate. ``IssueLifecycle`` renders
a blocked transition as "blocked by N failing gate check(s)" and then iterates
the failures. If an unobservable result blocks while living outside that bucket,
a naive caller prints *blocked by 0 failing gate check(s)* and lists nothing — a
refusal that names no reason, which is its own species of the defect this WMBT
closes. So the outcome must expose the full blocking set, not only the failures.

RED state: ``atdd.coach.gate.decision`` declares no ``GateVerdict``.
"""
from __future__ import annotations

import pytest

from atdd.coach.gate.decision import GateCheckResult, GateVerdict, evaluate_gate

pytestmark = [pytest.mark.platform]

_RULE = "repo.govern-lifecycle.c013"


@pytest.fixture()
def mixed_outcome():
    """One honest failure and one unmade observation, in the same run."""
    return evaluate_gate(
        [
            GateCheckResult.failing("GT-BROKEN", _RULE, "the assertion did not hold"),
            GateCheckResult.could_not_check("GT-BLIND", _RULE, "no provider was registered"),
        ]
    )


def test_the_unobservable_check_is_not_counted_as_a_failure(mixed_outcome):
    """An unmade observation must never be reported as a discovered fault."""
    failure_ids = [r.gate_id for r in mixed_outcome.failures]

    assert failure_ids == ["GT-BROKEN"], (
        f"the failures bucket must hold only checks that observed a violation; got {failure_ids}"
    )


def test_the_unobservable_check_is_reported_in_its_own_bucket(mixed_outcome):
    """And attributably, so the operator knows which check went blind."""
    assert [r.gate_id for r in mixed_outcome.unobservable] == ["GT-BLIND"]

    blind = mixed_outcome.unobservable[0]
    assert blind.verdict is GateVerdict.COULD_NOT_CHECK
    assert blind.rule_id == _RULE, "the refusal must carry the rule it could not enforce"
    assert blind.message, "the refusal must say something about what could not be observed"


def test_every_verdict_survives_into_the_full_results_record(mixed_outcome):
    """Partitioning into buckets must not drop anything from the record."""
    assert len(mixed_outcome.results) == 2
    assert {r.gate_id for r in mixed_outcome.results} == {"GT-BROKEN", "GT-BLIND"}
    assert mixed_outcome.proceed is False


def test_a_refusal_is_never_rendered_as_blocked_by_zero_checks():
    """The caller-facing guard: an unobservable-only block still names a blocker.

    ``IssueLifecycle._run_transition_gate`` counts the blocking set before
    printing it. With only ``failures`` available that count is zero here, and
    the operator is told the transition is blocked by nothing at all.
    """
    outcome = evaluate_gate(
        [
            GateCheckResult.passing("GT-OK", _RULE, "observed and satisfied"),
            GateCheckResult.could_not_check("GT-BLIND", _RULE, "could not list the PRs"),
        ]
    )

    assert outcome.proceed is False
    assert outcome.failures == (), "nothing here observed a violation"
    assert len(outcome.blockers) == 1, (
        "the outcome must expose the full blocking set, or a caller that renders "
        "only `failures` reports a refusal blocked by zero checks"
    )
    assert outcome.blockers[0].gate_id == "GT-BLIND"
