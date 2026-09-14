# URN: test:drive-state-machine:coach-state-machine-and-runtime:C003-UNIT-001-an-approval-does-not-survive-a-new-commit
# Acceptance: acc:drive-state-machine:C003-UNIT-001-an-approval-does-not-survive-a-new-commit
# WMBT: wmbt:drive-state-machine:C003
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C003-UNIT-001 — an approval given at one commit does not verify at the next.

`build_token` signs (issue, from_phase, to_phase, branch, expires_at) and no
commit enters `canonical_scope`. Reproduced 2026-09-13 against the shipped
signer in a throwaway repo: mint at A, real commit B, verify -> True, while every
binding that IS signed refused as designed (different branch False, past expiry
False, different edge False).

THE SECOND COMMIT IS REAL, AND THAT IS THE POINT. Editing the recorded head
inside the token already fails today's signature check — `verify_token`
recomputes the message from the token's own body — so a test that mutates the
field passes without any content binding existing. Only moving the WORLD while
the token stays byte-identical exercises the defect.

RED state: `build_token` / `verify_token` accept no `head` argument — the scope
has no commit component to sign, so these calls fail until GREEN widens it. Same
convention as C010-UNIT-001, whose RED state was "there is no branch argument".
"""
from __future__ import annotations

import subprocess

import pytest

from atdd.coach.gate.approval import build_token, verify_token

pytestmark = [pytest.mark.platform]

_KEY = "operator-secret-key"
_ISSUE, _FROM, _TO = 2005, "SMOKE", "REFACTOR"
_BRANCH = "feat/c003-lab"
_NOW = "2026-09-13T12:00:00+00:00"
_EXPIRES = "2026-09-14T12:00:00+00:00"


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo_at_commit_a(tmp_path):
    """A real repository on a real branch. Returns (path, sha_a)."""
    repo = tmp_path / "work"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "lab@example.invalid")
    _git(repo, "config", "user.name", "Lab")
    (repo / "f.txt").write_text("seed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")
    _git(repo, "checkout", "-qb", _BRANCH)
    (repo / "f.txt").write_text("the content the operator reviewed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "the commit the operator reviewed")
    return repo, _git(repo, "rev-parse", "HEAD")


def _push_a_real_commit(repo):
    """What an agent does between the approval and the merge."""
    (repo / "f.txt").write_text("content the operator never saw\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "pushed after the approval")
    return _git(repo, "rev-parse", "HEAD")


def test_a_token_minted_at_a_does_not_verify_at_b(repo_at_commit_a):
    repo, sha_a = repo_at_commit_a

    token = build_token(
        _ISSUE, _FROM, _TO,
        approved_by="operator", approved_at=_NOW,
        branch=_BRANCH, expires_at=_EXPIRES, head=sha_a, key=_KEY,
    )

    # The approval still applies to the content it was given for.
    assert verify_token(token, _ISSUE, _FROM, _TO, _KEY,
                        branch=_BRANCH, now=_NOW, head=sha_a) is True, (
        "the token must verify at the commit it was minted for; a binding that "
        "refuses its own commit is a broken gate, not a strict one"
    )

    sha_b = _push_a_real_commit(repo)
    assert sha_b != sha_a, "the lab did not actually move the branch"

    assert verify_token(token, _ISSUE, _FROM, _TO, _KEY,
                        branch=_BRANCH, now=_NOW, head=sha_b) is False, (
        f"the approval given for {sha_a[:9]} still verifies at {sha_b[:9]}. The "
        "operator reviewed the diff and the CI result at one commit; the sign-off "
        "is being spent on content nobody approved."
    )


def test_the_token_records_the_commit_it_was_given_for(repo_at_commit_a):
    """A signature that cannot say WHICH content it covers is not a content bind."""
    _repo, sha_a = repo_at_commit_a

    token = build_token(
        _ISSUE, _FROM, _TO,
        approved_by="operator", approved_at=_NOW,
        branch=_BRANCH, expires_at=_EXPIRES, head=sha_a, key=_KEY,
    )

    recorded = [v for v in token.values() if isinstance(v, str) and v == sha_a]
    assert recorded, (
        "no field of the token carries the commit it was minted for, so nothing "
        f"reading the token can tell which content was approved. fields: "
        f"{sorted(token)}"
    )
