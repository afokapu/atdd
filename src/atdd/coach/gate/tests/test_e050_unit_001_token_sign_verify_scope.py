# URN: test:govern-lifecycle:operator-approval-token-gate:E050-UNIT-001-token-presence-and-scope-and-signature-are-pure
# Acceptance: acc:govern-lifecycle:E050-UNIT-001-token-presence-and-scope-and-signature-are-pure
# WMBT: wmbt:govern-lifecycle:E050
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E050-UNIT-001 — the pure approval-token verifier (sign / verify / scope).

verify_token accepts a correctly operator-signed token for the EXACT
(issue, from, to) transition and rejects everything else: a token scoped to a
DIFFERENT transition (a PLANNED->RED token never unlocks RED->GREEN), a token
whose signature is wrong/forged, and a structurally absent token. All pure —
no filesystem, no subprocess (the file-reading lives in the GateCheck sibling).

RED state: there is no atdd.coach.gate.approval module.
"""
from __future__ import annotations

import pytest

from atdd.coach.gate.approval import (
    build_token,
    sign_approval,
    verify_token,
)

pytestmark = [pytest.mark.platform]

_KEY = "operator-secret-key"


def test_matching_signed_token_verifies_true():
    token = build_token(1017, "PLANNED", "RED", approved_by="alec", approved_at="t", key=_KEY)
    assert verify_token(token, 1017, "PLANNED", "RED", key=_KEY) is True


def test_token_for_a_different_transition_does_not_unlock_another():
    # A token signed for PLANNED->RED must NOT satisfy RED->GREEN (scope isolation).
    token = build_token(1017, "PLANNED", "RED", approved_by="alec", approved_at="t", key=_KEY)
    assert verify_token(token, 1017, "RED", "GREEN", key=_KEY) is False
    # ... nor a token for a different issue.
    assert verify_token(token, 9999, "PLANNED", "RED", key=_KEY) is False


def test_forged_or_absent_signature_verifies_false():
    good = build_token(1017, "PLANNED", "RED", approved_by="alec", approved_at="t", key=_KEY)
    forged = dict(good)
    forged["signature"] = "deadbeef"  # not sign_approval over the scope
    assert verify_token(forged, 1017, "PLANNED", "RED", key=_KEY) is False

    missing_sig = {k: v for k, v in good.items() if k != "signature"}
    assert verify_token(missing_sig, 1017, "PLANNED", "RED", key=_KEY) is False

    # A signature made under a DIFFERENT key fails when checked under _KEY.
    wrong_key = build_token(1017, "PLANNED", "RED", approved_by="x", approved_at="t", key="other")
    assert verify_token(wrong_key, 1017, "PLANNED", "RED", key=_KEY) is False


def test_absent_token_verifies_false():
    assert verify_token(None, 1017, "PLANNED", "RED", key=_KEY) is False
    assert verify_token({}, 1017, "PLANNED", "RED", key=_KEY) is False


def test_sign_approval_is_deterministic_and_scope_sensitive():
    a = sign_approval(1017, "PLANNED", "RED", key=_KEY)
    assert a == sign_approval(1017, "PLANNED", "RED", key=_KEY)
    assert a != sign_approval(1017, "RED", "GREEN", key=_KEY)
