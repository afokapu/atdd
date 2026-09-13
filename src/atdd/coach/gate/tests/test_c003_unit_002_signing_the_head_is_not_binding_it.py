# URN: test:drive-state-machine:coach-state-machine-and-runtime:C003-UNIT-002-signing-the-head-is-not-binding-it
# Acceptance: acc:drive-state-machine:C003-UNIT-002-signing-the-head-is-not-binding-it
# WMBT: wmbt:drive-state-machine:C003
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C003-UNIT-002 — signing the head makes it tamper-evident; comparing binds it.

THIS ACCEPTANCE EXISTS BECAUSE THE FIRST WORDING OF THE DELIVERABLE DID NOT WORK.

#2005 Phase 1 Deliverable 1 originally read, in full: "The head SHA joins the
signed scope, resolved identically at mint and at check." Implemented exactly
that way — and in the ONLY shape that keeps the existing corpus verifying, which
is to recompute the message from the token's own body the way `token_actor` reads
the actor — it measured, 2026-09-13:

                                                     at A     at B
    Deliverable 1 as written (signed scope only)     True     True
    Deliverable 1 + an explicit head comparison      True    False

The message is recomputed from what the token SAYS, so it is the same string at
both commits. The signature proves the field was not edited; it cannot notice
that the world moved. The refusal needs a second, separate comparison against the
currently-resolved head — the shape the expiry already uses through `now`.

An acceptance that specifies a mechanism which cannot produce its own Done-when
is the #1888 shape, and every gate below it would have enforced it faithfully.
So both halves are asserted here, separately.

RED state: no `head` argument exists on `build_token` / `verify_token`.
"""
from __future__ import annotations

import pytest

from atdd.coach.gate.approval import build_token, verify_token

pytestmark = [pytest.mark.platform]

_KEY = "operator-secret-key"
_ISSUE, _FROM, _TO = 2005, "SMOKE", "REFACTOR"
_BRANCH = "feat/c003-lab"
_NOW = "2026-09-13T12:00:00+00:00"
_EXPIRES = "2026-09-14T12:00:00+00:00"
_SHA_A = "99af6ffbbfa8c1a88645cbcfc99820dd543dafee"
_SHA_B = "91e5ba3e591cfb063ab02adafde6f04438ae68eb"


def _token(head=_SHA_A):
    return build_token(
        _ISSUE, _FROM, _TO,
        approved_by="operator", approved_at=_NOW,
        branch=_BRANCH, expires_at=_EXPIRES, head=head, key=_KEY,
    )


def _verify(token, head):
    return verify_token(token, _ISSUE, _FROM, _TO, _KEY,
                        branch=_BRANCH, now=_NOW, head=head)


# -- the BINDING half: a differing current head is refused -------------------- #
def test_a_differing_current_head_is_refused():
    token = _token()

    assert _verify(token, _SHA_A) is True
    assert _verify(token, _SHA_B) is False, (
        "the token verifies against a head it does not name. Signing the value "
        "is not the same as checking it: the recomputed message is identical at "
        "both commits, so only an explicit comparison can refuse here."
    )


# -- the TAMPER-EVIDENCE half: the recorded head cannot be edited ------------- #
def test_editing_the_recorded_head_breaks_the_signature():
    token = _token()
    token["head"] = _SHA_B

    assert _verify(token, _SHA_B) is False, (
        "the recorded head was rewritten in place and the token still verifies, "
        "so the audit trail can be edited without detection"
    )


def test_stripping_the_recorded_head_breaks_the_signature():
    """Removing the field must not be a way out of the binding.

    A token minted WITH a head and then stripped of it must not fall back to the
    headless regime — otherwise the escape from content binding is one `del`.
    """
    token = _token()
    token.pop("head", None)

    assert _verify(token, _SHA_B) is False, (
        "stripping the recorded head lets the token verify against any commit; "
        "the back-compat path for genuinely headless tokens must not be "
        "reachable by deleting the field from a head-bearing one"
    )


def test_both_halves_are_needed():
    """Neither half alone closes the defect — stated as one assertion.

    Measured: the signed scope alone returns True at A and True at B. If this
    test ever passes while `test_a_differing_current_head_is_refused` fails, the
    implementation has signed the head without comparing it, which is exactly the
    version the original deliverable described.
    """
    token = _token()

    signed_and_compared = (_verify(token, _SHA_A), _verify(token, _SHA_B))

    assert signed_and_compared == (True, False), (
        "the token must verify at the commit it names and refuse at any other. "
        f"got (at A, at B) = {signed_and_compared}. (True, True) means the head "
        "is signed but never compared — tamper-evidence without binding."
    )
