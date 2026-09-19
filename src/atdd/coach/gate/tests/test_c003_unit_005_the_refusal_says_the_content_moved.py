# URN: test:drive-state-machine:coach-state-machine-and-runtime:C003-UNIT-005-the-refusal-says-the-content-moved
# Acceptance: acc:drive-state-machine:C003-UNIT-005-the-refusal-says-the-content-moved
# WMBT: wmbt:drive-state-machine:C003
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C003-UNIT-005 — four refusals, four different operator actions, four sentences.

`ApprovalTokenGateCheck._diagnose` already recovers WHY a bound token failed by
re-running the same pure verifier with narrowed inputs — expired, branch rebound,
branchless, or scope/signature mismatch. Content drift is a fifth cause and needs
its own sentence, because the action it calls for is different from all of them:

    expired            -> re-approve, nothing about the work changed
    branch rebound     -> the work moved to a different branch
    content moved      -> re-review THIS diff, then re-approve
    signature mismatch -> suspect tampering

A gate that refuses without naming its cause leaves the operator to guess between
those, which is the defect this program is named for in miniature — the wording
`approval_check`'s own module docstring uses.

RED state: `_diagnose` has no content-moved branch; no `head` argument exists.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_KEY = "operator-secret-key"
_ISSUE, _FROM, _TO = 2005, "SMOKE", "REFACTOR"
_BRANCH = "feat/c003-lab"
_NOW = "2026-09-13T12:00:00+00:00"
_EXPIRES = "2026-09-14T12:00:00+00:00"
_LATER = "2026-09-20T12:00:00+00:00"
_SHA_A = "99af6ffbbfa8c1a88645cbcfc99820dd543dafee"
_SHA_B = "91e5ba3e591cfb063ab02adafde6f04438ae68eb"


def _token(**over):
    from atdd.coach.gate.approval import build_token

    kwargs: dict = dict(approved_by="operator", approved_at=_NOW, branch=_BRANCH,
                  expires_at=_EXPIRES, head=_SHA_A, key=_KEY)
    kwargs.update(over)
    return build_token(_ISSUE, _FROM, _TO, **kwargs)


def _diagnose(token, *, branch=_BRANCH, now=_NOW, head=_SHA_A):
    from atdd.coach.gate.approval_check import ApprovalTokenGateCheck
    from atdd.coach.gate.decision import GateContext

    check = ApprovalTokenGateCheck(signing_key=_KEY, now=now)
    ctx = GateContext(issue_number=_ISSUE, from_phase=_FROM, to_phase=_TO,
                      worktree=Path("."))
    return check._diagnose(token, ctx, _KEY, branch, now, head)


def test_content_drift_says_the_content_moved():
    text = _diagnose(_token(), head=_SHA_B).lower()

    assert "content" in text or "commit" in text or "advanced" in text, (
        f"the refusal does not say the content moved: {text!r}"
    )
    assert "expire" not in text, (
        f"content drift is being reported as an expiry: {text!r}"
    )


def test_content_drift_is_distinguishable_from_expiry():
    drift = _diagnose(_token(), head=_SHA_B)
    expired = _diagnose(_token(), now=_LATER, head=_SHA_A)

    assert drift != expired, (
        "a token refused because the branch advanced and one refused because it "
        f"aged produce the same sentence: {drift!r}"
    )
    assert "expire" in expired.lower(), (
        f"the expiry refusal no longer names the expiry: {expired!r}"
    )


def test_content_drift_is_distinguishable_from_a_rebound_branch():
    drift = _diagnose(_token(), head=_SHA_B)
    rebound = _diagnose(_token(), branch="feat/somewhere-else")

    assert drift != rebound, (
        "content drift and a rebound branch produce the same sentence; the first "
        "means re-review this diff, the second means the work moved elsewhere. "
        f"got: {drift!r}"
    )


def test_the_refusal_names_both_commits():
    """An operator cannot act on "the content moved" without knowing from what."""
    text = _diagnose(_token(), head=_SHA_B)

    assert _SHA_A[:7] in text and _SHA_B[:7] in text, (
        "the refusal names neither the approved commit nor the current one, so "
        "the operator cannot tell what changed or review the difference. "
        f"got: {text!r}"
    )
