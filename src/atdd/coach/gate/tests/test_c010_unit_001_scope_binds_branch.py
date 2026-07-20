# URN: test:govern-lifecycle:operator-approval-token-gate:C010-UNIT-001-scope-binds-branch
# Acceptance: acc:govern-lifecycle:C010-UNIT-001-scope-binds-branch
# WMBT: wmbt:govern-lifecycle:C010
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C010-UNIT-001 — the signed scope binds the BRANCH.

A token the operator signs while on branch A must verify on branch A and be
REJECTED when presented on branch B. Today ``canonical_scope`` signs only
``issue:FROM:TO`` (approval.py:32-34), so the signature is branch-blind and one
token verifies on every branch — the replay-across-branch defect measured live
on 2026-07-18 (19 of 19 main-signed tokens verifying from an unrelated
worktree). A token that verifies today regardless of branch is exactly what
this test catches.

RED state: ``build_token`` / ``verify_token`` accept no ``branch`` argument —
the scope has no branch component to sign, so these calls fail until GREEN
widens the signed scope. (Same convention as E050-UNIT-001, whose RED state is
"there is no atdd.coach.gate.approval module".)
"""
from __future__ import annotations

import pytest

from atdd.coach.gate.approval import build_token, verify_token

pytestmark = [pytest.mark.platform]

_KEY = "operator-secret-key"
_ISSUE, _FROM, _TO = 1525, "PLANNED", "RED"


def test_token_bound_to_its_signing_branch_is_rejected_on_another_branch():
    # The operator signs while checked out on feat/alpha.
    token = build_token(
        _ISSUE,
        _FROM,
        _TO,
        approved_by="operator",
        approved_at="2026-07-20T00:00:00Z",
        branch="feat/alpha",
        key=_KEY,
    )
    # It must still verify on the branch it was signed for (the guard discriminates,
    # it does not refuse everything)...
    assert (
        verify_token(token, _ISSUE, _FROM, _TO, branch="feat/alpha", key=_KEY) is True
    )
    # ...and must be REJECTED when the SAME token is presented on any other branch.
    # This is the assertion that stays RED until GREEN binds the branch into the
    # signed scope: today the token is branch-blind and this returns True.
    assert (
        verify_token(token, _ISSUE, _FROM, _TO, branch="feat/beta", key=_KEY) is False
    )


def test_token_carrying_no_branch_fails_closed_on_every_branch():
    # A token with no branch binding at all must not satisfy a branch-scoped
    # verification — fail-closed, no exception flow. Under the widened contract a
    # bound verification demands a bound token.
    token = build_token(
        _ISSUE,
        _FROM,
        _TO,
        approved_by="operator",
        approved_at="2026-07-20T00:00:00Z",
        key=_KEY,
    )
    assert (
        verify_token(token, _ISSUE, _FROM, _TO, branch="feat/alpha", key=_KEY) is False
    )
