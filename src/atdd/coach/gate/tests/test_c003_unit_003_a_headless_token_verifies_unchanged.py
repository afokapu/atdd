# URN: test:drive-state-machine:coach-state-machine-and-runtime:C003-UNIT-003-a-headless-token-verifies-unchanged
# Acceptance: acc:drive-state-machine:C003-UNIT-003-a-headless-token-verifies-unchanged
# WMBT: wmbt:drive-state-machine:C003
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C003-UNIT-003 — a token is read under the regime it was minted in.

Corpus census, 2026-09-13, walked with `os.walk` (never
`glob('**/approvals/*.json')`, which does not descend dotted directories and
returns 0 of 311 because every token lives under `.atdd/`):

    311 tokens   0 carrying a head under any key
    212 BOUND (branch and/or expiry)   99 PRE-BINDING (neither)
     29 still unexpired   183 expired   99 undated

So a missing head cannot be treated as a mismatch, and the whole corpus must
verify exactly as it does today.

THE TRAP, AND IT BREAKS ALL 311 AT ONCE. `branch` is passed IN from the resolver;
the head must be read OFF THE TOKEN, the way `token_actor` reads the actor. Those
two idioms sit in the same function, and choosing the `branch` one is the natural
mistake. Measured: reading it off the token left 311 of 311 corpus verdicts
unchanged; folding in the RESOLVED head made a headless token verify False.

The 99 pre-binding tokens matter twice over: `_pre_binding_verdict` passes no
branch and no clock, so they sit outside the new rule entirely unless it is wired
there too.

RED state: no `head` argument exists on `build_token` / `verify_token`.
"""
from __future__ import annotations

import pytest

from atdd.coach.gate.approval import build_token, verify_token

pytestmark = [pytest.mark.platform]

_KEY = "operator-secret-key"
_ISSUE, _FROM, _TO = 1525, "PLANNED", "RED"
_BRANCH = "feat/alpha"
_NOW = "2026-09-13T12:00:00+00:00"
_EXPIRES = "2026-09-14T12:00:00+00:00"
_RESOLVED_HEAD = "99af6ffbbfa8c1a88645cbcfc99820dd543dafee"


def test_a_pre_binding_token_verifies_unchanged():
    """99 of 311: no branch, no expiry, no schema_version regime concerns."""
    token = build_token(_ISSUE, _FROM, _TO,
                        approved_by="operator", approved_at=_NOW, key=_KEY)

    assert verify_token(token, _ISSUE, _FROM, _TO, _KEY) is True, (
        "a pre-binding token stopped verifying; 99 tokens in the corpus carry "
        "neither a branch nor an expiry and are accepted under the regime they "
        "were minted in"
    )


def test_a_branch_bound_headless_token_verifies_unchanged():
    """212 of 311: branch and expiry, but no head — the common live case."""
    token = build_token(_ISSUE, _FROM, _TO,
                        approved_by="operator", approved_at=_NOW,
                        branch=_BRANCH, expires_at=_EXPIRES, key=_KEY)

    assert verify_token(token, _ISSUE, _FROM, _TO, _KEY,
                        branch=_BRANCH, now=_NOW) is True, (
        "a branch-bound token carrying no head stopped verifying"
    )


def test_a_headless_token_is_not_refused_by_a_resolved_head():
    """THE TRAP, asserted directly.

    The check side resolves a head for the issue whether or not the token names
    one. If that resolved value is folded into the recomputed message, every one
    of the 311 headless tokens fails on the first commit.
    """
    token = build_token(_ISSUE, _FROM, _TO,
                        approved_by="operator", approved_at=_NOW,
                        branch=_BRANCH, expires_at=_EXPIRES, key=_KEY)

    assert verify_token(token, _ISSUE, _FROM, _TO, _KEY,
                        branch=_BRANCH, now=_NOW, head=_RESOLVED_HEAD) is True, (
        "a token that names no head was refused because the CHECK resolved one. "
        "A missing head is not a mismatch — the head must be recomputed from the "
        "token's own body (the `token_actor` pattern), never passed in from the "
        "resolver (the `branch` pattern). This single choice decides whether all "
        "311 existing tokens keep working."
    )


def test_the_headless_signature_is_byte_identical_to_todays():
    """Back-compat proved on the SCOPE, not just on the verdict.

    A verdict can agree by accident. If the signed message for a headless token
    is unchanged, every headless token in the corpus verifies unchanged by
    construction rather than by coincidence.
    """
    from atdd.coach.gate.approval import sign_approval

    today = sign_approval(_ISSUE, _FROM, _TO, _KEY,
                          branch=_BRANCH, expires_at=_EXPIRES, actor="operator")
    with_head_absent = sign_approval(_ISSUE, _FROM, _TO, _KEY,
                                     branch=_BRANCH, expires_at=_EXPIRES,
                                     actor="operator", head=None)

    assert today == with_head_absent, (
        "the signed message changed for a token that names no head, so the "
        "corpus cannot survive the change by construction"
    )
