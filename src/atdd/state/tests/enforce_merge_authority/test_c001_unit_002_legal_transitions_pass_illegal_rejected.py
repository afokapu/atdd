# URN: test:enforce-merge-authority:validate-transition-legality:C001-UNIT-002-legal-transitions-pass-illegal-rejected
# Acceptance: acc:enforce-merge-authority:C001-UNIT-002-legal-transitions-pass-illegal-rejected
# WMBT: wmbt:enforce-merge-authority:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: over a matrix drawn from the section-6 evidence table, the validator admits every legal pair (INIT->PLANNED, PLANNED->RED, RED->GREEN, GREEN->SMOKE with their evidence), rejects the backward GREEN->RED as non-monotonic, rejects a skip whose skipped gates carry no evidence, admits * -> TOMBSTONED only with a reason digest and tombstone metadata, and names the uid, the transition and the failed clause on every rejection. Refs #1400.
"""The section-6 evidence table, admitted and rejected pair by pair (C001-UNIT-002).

wagon: enforce-merge-authority | feature: validate-transition-legality | phase: RED
WMBT: wmbt:enforce-merge-authority:C001

The evidence model (spec §6) is a table, so the validator is tested as one. Three
properties fall out of it and each has its own row here:

- **monotonic** — ``GREEN -> RED`` is rejected however much evidence it carries, because
  no evidence makes "we un-implemented it" a legal *shared* claim;
- **no unevidenced skip** — a jump is legal exactly when it carries what every gate it
  skipped would have demanded (§7.2 clause 3), never because it looked close enough;
- **retirement is a record** — ``* -> TOMBSTONED`` is admitted only with a reason digest
  and tombstone metadata, and never as a file deletion (§10 rule 3).

Refs #1400.
"""
from __future__ import annotations

from typing import Set

import pytest

from atdd.state import evidence
from atdd.state.evidence import TOMBSTONED, check_transition

from ._helpers import UID_X

FULL: Set[str] = {
    "uid_generated", "body_initialized", "projection_digest",
    "plan_complete", "acceptance_or_wmbt_refs",
    "operator_token_digest", "gate_id", "failing_test_evidence",
    "passing_test_evidence", "implementation_diff",
    "smoke_evidence_artifact",
}

#: (before, after, evidence, legal) — the section-6 table, plus the ways to break it.
MATRIX = [
    # Legal: each gate with exactly the evidence §6 demands of it.
    ("INIT", "PLANNED", {"plan_complete", "acceptance_or_wmbt_refs"}, True),
    ("PLANNED", "RED",
     {"operator_token_digest", "gate_id", "failing_test_evidence"}, True),
    ("RED", "GREEN", {"passing_test_evidence", "implementation_diff"}, True),
    ("GREEN", "SMOKE", {"smoke_evidence_artifact"}, True),

    # Illegal: the same gates with their evidence withheld.
    ("INIT", "PLANNED", set(), False),
    ("PLANNED", "RED", {"gate_id"}, False),               # token digest withheld
    ("RED", "GREEN", {"implementation_diff"}, False),      # passing tests withheld
    ("GREEN", "SMOKE", set(), False),                      # no smoke artifact

    # Illegal: backward. Non-monotonic however much evidence it carries.
    ("GREEN", "RED", set(FULL), False),
    ("SMOKE", "PLANNED", set(FULL), False),

    # Skipping: legal ONLY with evidence for every gate skipped (§7.2 clause 3).
    ("PLANNED", "GREEN", set(), False),
    ("PLANNED", "GREEN", {"operator_token_digest", "gate_id", "failing_test_evidence"}, False),
    ("PLANNED", "GREEN", set(FULL), True),
    ("INIT", "SMOKE", set(FULL), True),

    # Retirement: a record, and only with one.
    ("GREEN", TOMBSTONED, set(), False),
    ("GREEN", TOMBSTONED, {"reason_digest"}, False),
    ("GREEN", TOMBSTONED, {"reason_digest", "tombstone_metadata"}, True),
    ("INIT", TOMBSTONED, {"reason_digest", "tombstone_metadata"}, True),

    # COMPLETE is DERIVED from merge-to-main and may never be stored (§18 decision 1).
    ("SMOKE", "COMPLETE", set(FULL), False),
]


@pytest.mark.parametrize(("before", "after", "have", "legal"), MATRIX)
def test_c001_unit_002_legal_transitions_pass_illegal_rejected(
    before: str, after: str, have: Set[str], legal: bool,
) -> None:
    """Every legal pair is admitted; every backward, skipping or unevidenced pair is not."""
    violations = check_transition(UID_X, before, after, have)

    if legal:
        assert violations == [], f"{before}->{after} with {sorted(have)} should be admitted"
        return

    assert violations, f"{before}->{after} with {sorted(have)} should be rejected"

    # Each rejection carries the uid, the attempted transition, and the failed clause.
    for violation in violations:
        assert violation.uid == UID_X
        assert violation.transition == f"{before}->{after}"
        assert violation.clause in (
            evidence.CLAUSE_NON_MONOTONIC,
            evidence.CLAUSE_SKIPPED_GATE,
            evidence.CLAUSE_MISSING_EVIDENCE,
            evidence.CLAUSE_TOMBSTONE_EVIDENCE,
            evidence.CLAUSE_COMPLETE_IS_DERIVED,
            evidence.CLAUSE_UNKNOWN_TRANSITION,
        )
        assert violation.detail

    clauses = {violation.clause for violation in violations}

    # A backward transition is rejected as non-monotonic — never as "missing evidence",
    # because there is no evidence that would have made it legal.
    if before in ("GREEN", "SMOKE") and after in ("RED", "PLANNED"):
        assert clauses == {evidence.CLAUSE_NON_MONOTONIC}
        assert "monotonic" in violations[0].detail

    # A skip is rejected naming the gate it skipped.
    if before == "PLANNED" and after == "GREEN":
        assert evidence.CLAUSE_SKIPPED_GATE in clauses
        assert any("PLANNED->RED" in v.detail or "RED->GREEN" in v.detail for v in violations)

    # Retirement without its record is rejected as such.
    if after == TOMBSTONED:
        assert clauses == {evidence.CLAUSE_TOMBSTONE_EVIDENCE}
        assert "tombstone" in violations[0].detail.lower()

    # A stored COMPLETE is invalid, not merely unevidenced.
    if after == "COMPLETE":
        assert clauses == {evidence.CLAUSE_COMPLETE_IS_DERIVED}
        assert "derived from merge-to-main" in violations[0].detail
