"""#1967 — a work item that produced knowledge, not behaviour, can say so.

An umbrella issue investigates a problem, decomposes it into child delivery
issues, and watches those children merge. It has then done its job, and until
``RESOLVED`` it could not say so: every exit was refused or wrong.

Measured against the shipped validator before this change (probe P09):

    INIT -> PLANNED     admissible on plan evidence alone
    INIT -> RED         skipped_gate        (demands failing_test_evidence)
    INIT -> GREEN       skipped_gate x2     (demands passing + implementation_diff)
    INIT -> SMOKE       skipped_gate x3     (demands a smoke artifact)
    *    -> COMPLETE    complete_is_derived (may never be stored)
    *    -> TOMBSTONED  admissible — but means "retired", not "succeeded"

So the umbrella stalled at PLANNED, and its only honest exits were to fabricate
test evidence it never produced or to be recorded as a retraction of work that
succeeded. ``RESOLVED`` is the missing outcome: success without code.

It is an ESCAPE, not a rung — beside the ladder like ``BLOCKED`` and
``OBSOLETE``, terminal, non-resumable, entered on an operator decision. The
sibling module's test pins why that is not a stylistic choice.
"""
from __future__ import annotations

import pytest

#: What an umbrella can honestly produce: a plan and children. No tests, no diff.
UMBRELLA = frozenset({
    "uid_generated", "body_initialized", "plan_complete",
    "acceptance_or_wmbt_refs", "projection_digest", "operator_token_digest",
})


def test_resolved_is_declared_an_escape():
    from atdd.state.evidence import ESCAPES

    assert "RESOLVED" in ESCAPES, (
        "RESOLVED must be an escape. As a rung it would give INIT two non-escape "
        "targets, spine() would raise, and the coach runtime would not import."
    )


def test_umbrella_with_no_test_evidence_reaches_resolved():
    """The whole point: no tests for work that produced none."""
    from atdd.state.evidence import check_transition

    violations = check_transition(
        "wi_umbrella", "INIT", "RESOLVED", UMBRELLA | {"conclusion_digest"})
    assert violations == [], [v.render() for v in violations]


def test_resolved_requires_a_conclusion():
    """An escape that records a RESULT must carry the result."""
    from atdd.state.evidence import CLAUSE_ESCAPE_EVIDENCE, check_transition

    violations = check_transition("wi_umbrella", "INIT", "RESOLVED", UMBRELLA)
    assert [v.clause for v in violations] == [CLAUSE_ESCAPE_EVIDENCE]
    assert "conclusion_digest" in violations[0].detail


def test_resolved_requires_an_operator_decision():
    from atdd.state.evidence import CLAUSE_ESCAPE_EVIDENCE, check_transition

    unsigned = (UMBRELLA - {"operator_token_digest"}) | {"conclusion_digest"}
    violations = check_transition("wi_umbrella", "INIT", "RESOLVED", unsigned)
    assert [v.clause for v in violations] == [CLAUSE_ESCAPE_EVIDENCE]


@pytest.mark.parametrize("target", ["PLANNED", "RED", "GREEN", "COMPLETE"])
def test_resolved_is_terminal_and_non_resumable(target):
    """Unlike BLOCKED, a resolved item does not come back. Reopening is a new object."""
    from atdd.state.evidence import (
        CLAUSE_TERMINAL_PHASE, RESUMABLE_ESCAPES, check_transition,
    )

    assert "RESOLVED" not in RESUMABLE_ESCAPES
    violations = check_transition("wi_umbrella", "RESOLVED", target, UMBRELLA)
    assert CLAUSE_TERMINAL_PHASE in [v.clause for v in violations]


def test_resolved_is_reachable_from_planned_too():
    """A umbrella that got as far as PLANNED before decomposing is still an umbrella."""
    from atdd.state.evidence import check_transition

    violations = check_transition(
        "wi_umbrella", "PLANNED", "RESOLVED", UMBRELLA | {"conclusion_digest"})
    assert violations == [], [v.render() for v in violations]


# --- the ladder must not move -------------------------------------------------

def test_phase_ladder_is_unchanged():
    from atdd.state.evidence import PHASE_LADDER

    assert PHASE_LADDER == (
        "INIT", "PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE")
    assert "RESOLVED" not in PHASE_LADDER, "an escape carries no rank"


def test_delivery_rungs_still_demand_what_they_demanded():
    from atdd.state.evidence import requires_for

    assert requires_for("INIT", "PLANNED") == ("plan_complete", "acceptance_or_wmbt_refs")
    assert requires_for("RED", "GREEN") == ("passing_test_evidence", "implementation_diff")


def test_resolved_does_not_launder_a_skipped_rung():
    """INIT -> RESOLVED must not become a cheap route to GREEN."""
    from atdd.state.evidence import check_transition

    violations = check_transition("wi_x", "PLANNED", "GREEN", UMBRELLA | {"conclusion_digest"})
    assert violations, "an unevidenced GREEN must still be refused"
