# URN: test:enforce-merge-authority:validate-transition-legality:C001-UNIT-001-illegal-phase-jump-is-admitted
# Acceptance: acc:enforce-merge-authority:C001-UNIT-001-illegal-phase-jump-is-admitted
# WMBT: wmbt:enforce-merge-authority:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: a canonical, schema-valid projection that jumps PLANNED->GREEN with no failing-test evidence and no operator token digest passes canonicality and schema and is REJECTED by the legal-transition validator, whose report names the skipped gate PLANNED->RED and the evidence it is missing. Refs #1400.
"""Canonical is not correct: the illegal phase jump is rejected (C001-UNIT-001).

wagon: enforce-merge-authority | feature: validate-transition-legality | phase: RED
WMBT: wmbt:enforce-merge-authority:C001

This is the acceptance the whole wagon exists for. A projection that jumps
``PLANNED -> GREEN`` without ever going RED — no operator token, no failing test — is
*byte-perfect canonical* and *schema-valid*. Every check that shipped before this one
admits it. It is still a lie about what happened, and merging it puts that lie in the
shared source of truth.

So this test proves both halves: the earlier checks really do admit the jump (that is the
gap, not a strawman), and the legal-transition validator really does reject it, naming the
gate it skipped and the evidence it never carried. Refs #1400.
"""
from __future__ import annotations

from atdd.state import evidence
from atdd.state.projection import check_canonicality, validate_document

from ._helpers import UID_X, document, write_projection


def test_c001_unit_001_illegal_phase_jump_is_admitted(tmp_path) -> None:
    """The jump passes canonicality and schema, and the transition validator rejects it."""
    base = {UID_X: document(UID_X, phase="PLANNED")}
    head = {UID_X: document(UID_X, phase="GREEN")}

    # The head projection is canonical — project(hydrate(p)) == p, byte for byte...
    write_projection(tmp_path, head.values())
    assert check_canonicality(tmp_path).ok

    # ...and schema-valid. Every gate that existed before this wagon admits it.
    validate_document(head[UID_X])

    # It carries NO failing-test evidence and NO operator token digest.
    report = evidence.validate_projection_diff(base, head, {UID_X: set()})

    # The validator reports an illegal transition PLANNED->GREEN.
    assert not report.ok
    assert report.checked == 1
    violations = report.violations
    assert all(v.uid == UID_X for v in violations)
    assert all(v.transition == "PLANNED->GREEN" for v in violations)

    # The report names the SKIPPED gate (PLANNED->RED) and the evidence it is missing.
    rendered = report.render()
    assert "PLANNED->RED" in rendered
    assert "(skipped)" in rendered
    assert "operator_token_digest" in rendered
    assert "failing_test_evidence" in rendered
    assert "gate_id" in rendered

    # And the gate it jumped INTO is named too: RED->GREEN wanted passing tests and a diff.
    assert "RED->GREEN" in rendered
    assert "passing_test_evidence" in rendered
    assert "implementation_diff" in rendered

    # Every rejection carries the uid, the attempted transition, and the failed clause.
    assert {v.clause for v in violations} == {evidence.CLAUSE_SKIPPED_GATE}
    assert UID_X in rendered

    # The same jump WITH evidence for every skipped gate is admissible (spec §7.2 clause 3):
    # the jump is not forbidden because it skips RED, but because it skipped RED's evidence.
    evidenced = evidence.validate_projection_diff(base, head, {UID_X: {
        "operator_token_digest", "gate_id", "failing_test_evidence",
        "passing_test_evidence", "implementation_diff",
    }})
    assert evidenced.ok
