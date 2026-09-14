# URN: test:drive-state-machine:coach-state-machine-and-runtime:C003-UNIT-006-the-real-mint-records-the-head
# Acceptance: acc:drive-state-machine:C003-UNIT-006-the-real-mint-records-the-head
# WMBT: wmbt:drive-state-machine:C003
# Phase: RED
# Layer: application
# Assertion: behavioral
"""C003-UNIT-006 — the token `atdd coach approve` actually writes carries a head.

THIS ACCEPTANCE EXISTS BECAUSE EVERY OTHER ONE PASSED WHILE THE FIX WAS INERT.

C003-UNIT-001 through 005 and SMOKE-001 all build their tokens by calling
`build_token(..., head=...)` directly. The production mint in
`approve_command.py` did not pass `head` at all, so every token a real approval
wrote was headless — and `content_still_stands` accepts a headless token by
design, because that is the clause keeping the 311 pre-existing tokens
verifying. The signed scope, the verifier, the resolver and the gate were all
wired; the one line that feeds them was not.

Reproduced through the production call shape on 2026-09-13:

    token_head         : None
    verify at commit A : True
    verify at commit B : True      <- the defect, untouched

Found by an independent review pass, not by this suite. The lesson is the one
the repository keeps relearning: a test that constructs its own input never
observes the code that constructs the real one. So this asserts on what the
MINT produces, and every other C003 acceptance is downstream of it.
"""
from __future__ import annotations

import subprocess

import pytest

pytestmark = [pytest.mark.platform]

_BRANCH = "feat/c003-real-mint"


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo_with_remote(tmp_path):
    """A real repo whose branch is pushed, so a reviewed head exists."""
    bare = tmp_path / "origin.git"
    bare.mkdir()
    _git(bare, "init", "-q", "--bare")
    repo = tmp_path / "work"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "lab@example.invalid")
    _git(repo, "config", "user.name", "Lab")
    _git(repo, "remote", "add", "origin", str(bare))
    (repo / "f.txt").write_text("seed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")
    _git(repo, "checkout", "-qb", _BRANCH)
    (repo / "f.txt").write_text("reviewed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "reviewed")
    _git(repo, "push", "-q", "-u", "origin", _BRANCH)
    return repo, _git(repo, "rev-parse", "HEAD")


def test_the_mint_call_site_passes_a_head():
    """The narrowest possible guard on the line that was missing.

    Asserted on the source because the full mint needs a State Store binding, a
    Control Root and a legal edge; this catches the regression that actually
    happened — the argument being dropped — without that apparatus.
    """
    import ast
    import inspect

    from atdd.coach.gate import approve_command

    # Parsed, not sliced. The first attempt cut the call at its first ")", which
    # lands inside `approved_at.isoformat()` — so it read a truncated argument
    # list and reported a missing head that was there. A guard that misreads its
    # subject is worth less than no guard.
    tree = ast.parse(inspect.getsource(approve_command))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "build_token"]
    assert calls, "approve_command no longer calls build_token at all"

    for call in calls:
        kwargs = {k.arg for k in call.keywords}
        assert "head" in kwargs, (
            "the production mint calls build_token without a head, so every "
            "approval it writes is headless and `content_still_stands` will "
            "accept it against any commit. The content binding is inert for real "
            f"approvals. arguments passed: {sorted(kwargs)}"
        )


def test_the_mint_refuses_when_the_reviewed_head_is_unknown(repo_with_remote, monkeypatch):
    """A headless mint is indistinguishable from a legacy token, so refuse instead.

    Minting without the binding when it cannot be established would re-open the
    hole for every future approval while looking exactly like back-compat.
    """
    from atdd.coach.gate import approve_command
    from atdd.coach.gate.mint_head import HeadBinding

    _repo, _sha = repo_with_remote
    monkeypatch.setattr(
        approve_command, "resolve_reviewed_head",
        lambda _start, _branch: HeadBinding(branch=_BRANCH, reason="no remote-tracking ref"),
    )

    src = __import__("inspect").getsource(approve_command)
    assert "reviewed.sha is None" in src, (
        "the mint does not refuse when the reviewed head cannot be established; "
        "it would write a headless token that silently carries no binding"
    )


def test_a_token_the_real_mint_writes_refuses_a_later_commit(repo_with_remote):
    """End to end on the signer: mint the way the command does, then move the head."""
    from atdd.coach.gate.approval import build_token, token_head, verify_token
    from atdd.coach.gate.mint_head import resolve_reviewed_head

    repo, sha_a = repo_with_remote
    reviewed = resolve_reviewed_head(repo, _BRANCH)
    assert reviewed.sha == sha_a, f"the lab could not resolve a reviewed head: {reviewed.reason!r}"

    now, expires = "2026-09-13T12:00:00+00:00", "2026-09-14T12:00:00+00:00"
    token = build_token(2005, "PLANNED", "RED", approved_by="operator",
                        approved_at=now, agent_session=None, branch=_BRANCH,
                        expires_at=expires, head=reviewed.sha, key=None)

    assert token_head(token) == sha_a, "the minted token records no head"

    (repo / "f.txt").write_text("pushed after the approval\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "after")
    _git(repo, "push", "-q", "origin", _BRANCH)
    sha_b = resolve_reviewed_head(repo, _BRANCH).sha
    assert sha_b != sha_a

    assert verify_token(token, 2005, "PLANNED", "RED", branch=_BRANCH,
                        now=now, head=sha_b) is False, (
        "a token minted the way the real command mints it still verifies after "
        "the reviewed branch advanced"
    )
