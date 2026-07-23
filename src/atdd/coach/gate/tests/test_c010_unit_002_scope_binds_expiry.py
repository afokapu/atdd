# URN: test:govern-lifecycle:operator-approval-token-gate:C010-UNIT-002-scope-binds-expiry
# Acceptance: acc:govern-lifecycle:C010-UNIT-002-scope-binds-expiry
# WMBT: wmbt:govern-lifecycle:C010
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C010-UNIT-002 — the signed scope binds an EXPIRY.

A token carries a signed expiry and stops verifying once ``now`` is past it.
Today the token has no time component at all — ``canonical_scope`` signs only
``issue:FROM:TO`` — so a token is eternal: minted once, it verifies forever. A
token that never expires is exactly what this test catches.

``now`` is passed explicitly so the test needs no wall-clock sleep and is
deterministic.

RED state: ``build_token`` accepts no ``expires_at`` and ``verify_token``
accepts no ``now`` — there is no expiry to sign or compare, so these calls fail
until GREEN adds the time binding.
"""
from __future__ import annotations

import pytest

from atdd.coach.gate.approval import build_token, verify_token

pytestmark = [pytest.mark.platform]

_KEY = "operator-secret-key"
_ISSUE, _FROM, _TO = 1525, "PLANNED", "RED"


def test_token_verifies_before_expiry_and_is_rejected_after():
    token = build_token(
        _ISSUE,
        _FROM,
        _TO,
        approved_by="operator",
        approved_at="2026-07-20T00:00:00Z",
        branch="feat/alpha",
        expires_at="2026-07-20T00:05:00Z",
        key=_KEY,
    )
    # Before the expiry the token verifies...
    assert (
        verify_token(
            token,
            _ISSUE,
            _FROM,
            _TO,
            branch="feat/alpha",
            now="2026-07-20T00:04:00Z",
            key=_KEY,
        )
        is True
    )
    # ...and after the expiry it is rejected. This is the assertion that stays RED
    # until GREEN binds an expiry: today a minted token is eternal.
    assert (
        verify_token(
            token,
            _ISSUE,
            _FROM,
            _TO,
            branch="feat/alpha",
            now="2026-07-20T00:06:00Z",
            key=_KEY,
        )
        is False
    )


def test_token_with_absent_or_malformed_expiry_fails_closed():
    # An expiry that is absent, empty, or non-parseable must verify False without an
    # exception escaping the pure verifier (fail-closed) once verification is
    # time-aware.
    token = build_token(
        _ISSUE,
        _FROM,
        _TO,
        approved_by="operator",
        approved_at="2026-07-20T00:00:00Z",
        branch="feat/alpha",
        expires_at="not-a-timestamp",
        key=_KEY,
    )
    assert (
        verify_token(
            token,
            _ISSUE,
            _FROM,
            _TO,
            branch="feat/alpha",
            now="2026-07-20T00:04:00Z",
            key=_KEY,
        )
        is False
    )
