# URN: test:state-store:evidence:declared-escapes-are-walkable
# Issue: #1947 (#1400)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""A declared escape can actually be taken — and taken back (#1947).

Three shipped components disagreed about ``INIT -> OBSOLETE``. The phase machine
declares the edge, :data:`atdd.state.projection.PHASES` accepts ``OBSOLETE`` as a
committed value, and :func:`atdd.state.evidence.check_transition` refused it
``unknown_transition``: the escapes are deliberately off :data:`PHASE_LADDER` —
they order against nothing, so they have no rung — and nothing had been put in
their place, so the ranking branch swallowed them. The refusal was not even
honest about itself: ``unknown_transition`` says the edge does not exist, while
the convention plainly declares it.

This is the same defect #1602 fixed for ``SMOKE -> REFACTOR``, in the one form
that fix could not reach, so it is asserted the same way: **walked out of the
authored convention**, never against a literal list of edges this test invented.
An edge added to ``phase_machine.convention.yaml`` tomorrow is covered here today.

The escapes are gated, not waved through. Entering one demands the operator
sign-off digest, because entering an escape is never autonomous. Leaving
``BLOCKED`` demands that digest too — an escape is symmetric — plus the evidence
the rung it lands on implies, because ``BLOCKED`` kept no rank and a resume
cannot inherit a position it can no longer prove. ``OBSOLETE`` declares no way
out at all and is refused by name rather than by silence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Set

import pytest
import yaml

from atdd.state.evidence import (
    CLAUSE_ESCAPE_EVIDENCE,
    CLAUSE_MISSING_EVIDENCE,
    CLAUSE_SKIPPED_GATE,
    CLAUSE_TERMINAL_PHASE,
    CLAUSE_UNKNOWN_TRANSITION,
    ESCAPES,
    EVIDENCE_POLICY,
    PHASE_LADDER,
    RESUMABLE_ESCAPES,
    TOMBSTONED,
    check_transition,
    requires_for,
)

_REPO = Path(__file__).resolve().parents[4]
_CONVENTION = (
    _REPO / "src" / "atdd" / "coach" / "conventions" / "phase_machine.convention.yaml"
)
_SCHEMA = _REPO / "contracts" / "commons" / "projection-evidence.schema.json"

#: The sign-off an escape is entered and left by (phase_machine.convention.yaml:
#: "entering an escape is never autonomous"). It reaches CI as a digest, never as a
#: token (I8), which is why this is the token name the policy asks for.
OPERATOR = "operator_token_digest"


@pytest.fixture(scope="module")
def phase_machine() -> Dict[str, dict]:
    if not _CONVENTION.is_file():
        pytest.fail(f"authored phase machine missing: {_CONVENTION}")
    return yaml.safe_load(_CONVENTION.read_text(encoding="utf-8"))["phases"]


def _clauses(violations) -> List[str]:
    return [violation.clause for violation in violations]


def _walk_tokens(target: str) -> Set[str]:
    """Every token an object introduced at ``target`` owes: the mint, then each rung up to it."""
    tokens: Set[str] = set(requires_for(None, "INIT") or ())
    rungs = list(zip(PHASE_LADDER, PHASE_LADDER[1:]))[: PHASE_LADDER.index(target)]
    for lower, upper in rungs:
        tokens.update(requires_for(lower, upper) or ())
    return tokens


def test_the_escapes_are_the_phases_that_are_not_rungs(phase_machine) -> None:
    """Every declared phase is either a rung of the ladder or a named escape.

    A third kind would be a phase the evidence model can neither rank nor gate — which
    is precisely the state ``BLOCKED``/``OBSOLETE`` were in before this issue.
    """
    off_spine = set(phase_machine) - set(PHASE_LADDER)
    assert off_spine == set(ESCAPES), (
        f"phase_machine.convention.yaml declares {sorted(off_spine)} off the ladder while "
        f"evidence.ESCAPES names {sorted(ESCAPES)}; the difference is ungated"
    )


def test_every_declared_escape_edge_is_walkable(phase_machine) -> None:
    """The bug, stated over the whole convention rather than one edge of it.

    ``INIT -> OBSOLETE`` is the edge #1947 was filed on; every other rung declares the
    same two escapes, and all of them were refused identically.
    """
    refused = {}
    for source, spec in phase_machine.items():
        for target in spec.get("transitions_to") or ():
            if target not in ESCAPES:
                continue
            violations = check_transition("uid", source, target, [OPERATOR])
            if violations:
                refused[f"{source}->{target}"] = _clauses(violations)
    assert not refused, (
        f"the phase machine declares these escape edges and the merge authority refuses "
        f"them: {refused}"
    )


def test_an_unevidenced_escape_is_refused_as_policy_not_as_a_missing_edge() -> None:
    """The other half of the fix: gated, not waved through — and named when it fails.

    ``unknown_transition`` was the wrong answer twice over. It refused a legal escape,
    and it blamed the convention for an edge the convention declares.
    """
    violations = check_transition("uid", "INIT", "OBSOLETE", [])
    assert _clauses(violations) == [CLAUSE_ESCAPE_EVIDENCE], violations
    assert CLAUSE_UNKNOWN_TRANSITION not in _clauses(violations)
    assert OPERATOR in violations[0].detail


def test_every_declared_resume_out_of_blocked_is_walkable(phase_machine) -> None:
    """An escape you cannot leave is a trap, not an escape.

    ``BLOCKED`` declares a way back to every rung. The resume carries what that rung
    implies — the escape kept no rank, so there is nothing else it *could* be judged
    against — plus the operator sign-off that leaving an escape is.
    """
    refused = {}
    for target in phase_machine["BLOCKED"]["transitions_to"]:
        if target in ESCAPES:
            continue
        evidence = _walk_tokens(target) | {OPERATOR}
        violations = check_transition("uid", "BLOCKED", target, evidence)
        if violations:
            refused[f"BLOCKED->{target}"] = [v.render() for v in violations]
    assert not refused, f"declared resume edge(s) refused with full evidence: {refused}"


def test_a_resume_may_not_launder_a_skipped_gate() -> None:
    """``INIT -> BLOCKED -> GREEN`` owes exactly what ``INIT -> GREEN`` owed.

    This is what the resume rule is for. Admitting a resume on the operator's say-so
    alone would make the escape a way around every gate on the ladder — two signed
    hops and RED never happened.
    """
    violations = check_transition("uid", "BLOCKED", "GREEN", [OPERATOR])
    assert violations, "BLOCKED->GREEN with no test or implementation evidence was admitted"
    assert CLAUSE_UNKNOWN_TRANSITION not in _clauses(violations)
    assert set(_clauses(violations)) <= {CLAUSE_SKIPPED_GATE, CLAUSE_MISSING_EVIDENCE}
    assert any("failing_test_evidence" in v.detail for v in violations), violations


def test_leaving_blocked_without_the_operator_sign_off_is_refused_by_name() -> None:
    """Symmetry: entered by operator decision, left by one."""
    violations = check_transition("uid", "BLOCKED", "INIT", _walk_tokens("INIT"))
    assert _clauses(violations) == [CLAUSE_ESCAPE_EVIDENCE], violations
    assert OPERATOR in violations[0].detail


def test_obsolete_declares_no_way_out_and_says_so(phase_machine) -> None:
    """Terminal is a decision; ``unknown_transition`` would report it as an accident."""
    assert phase_machine["OBSOLETE"]["transitions_to"] == []
    assert "OBSOLETE" not in RESUMABLE_ESCAPES

    every_token = _walk_tokens("REFACTOR") | {OPERATOR}
    violations = check_transition("uid", "OBSOLETE", "RED", every_token)
    assert _clauses(violations) == [CLAUSE_TERMINAL_PHASE], violations


def test_retirement_still_outranks_an_escape() -> None:
    """Retiring a blocked object is a tombstone, not a resume: the older branch wins.

    ``* -> TOMBSTONED`` is checked before anything else and keeps its own evidence
    (#1580), which the new escape branches must not shadow or relax.
    """
    admitted = check_transition(
        "uid", "BLOCKED", TOMBSTONED, ["reason_digest", "tombstone_metadata"],
    )
    assert admitted == [], admitted

    refused = check_transition("uid", "BLOCKED", TOMBSTONED, [OPERATOR])
    assert _clauses(refused) == ["tombstone_evidence"], refused


def test_the_policy_is_a_valid_projection_evidence_document() -> None:
    """The table is data, so the contract it claims to be is worth asserting.

    The escape entries widened a document that names its own schema; an entry the
    schema would reject is a table core ships and could not load.
    """
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(instance=EVIDENCE_POLICY, schema=schema)
