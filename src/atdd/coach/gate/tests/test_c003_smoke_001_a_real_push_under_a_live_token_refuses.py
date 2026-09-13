# URN: test:drive-state-machine:coach-state-machine-and-runtime:C003-SMOKE-001-a-real-push-under-a-live-token-refuses
# Acceptance: acc:drive-state-machine:C003-SMOKE-001-a-real-push-under-a-live-token-refuses
# WMBT: wmbt:drive-state-machine:C003
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""C003-SMOKE-001 — real git, real token on disk, real gate: the push refuses it.

The unit acceptances exercise the signer directly. This one drives the whole
chain the way the lifecycle does: a token minted to the filesystem at the path
`approval_paths` resolves, a real commit landing on a real branch, and
`ApprovalTokenGateCheck.run` reading both back.

ASSERT ON THE FAR SIDE (README rule 2). The unit tests assert on `verify_token`,
which is the near side; every claim the broken binding makes is true of the
signer and false of the GATE. The gate is what refuses a transition, so the gate
is what this asserts on.

The token file is written and left byte-identical throughout. Only the WORLD
moves — which is the whole distinction this acceptance exists to hold, and the
reason a test that edits the token's recorded head proves nothing: editing it
already fails today's signature check.
"""
from __future__ import annotations

import json
import subprocess

import pytest

pytestmark = [pytest.mark.platform]

_KEY = "operator-secret-key"
_ISSUE, _FROM, _TO = 2005, "SMOKE", "REFACTOR"
_BRANCH = "feat/c003-smoke"
_NOW = "2026-09-13T12:00:00+00:00"
_EXPIRES = "2026-09-14T12:00:00+00:00"


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo_with_token(tmp_path, monkeypatch):
    """A real repo on a real branch with a real token file. Returns (repo, sha_a)."""
    from atdd.coach.gate.mint_head import _branch_head

    repo = tmp_path / "work"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "lab@example.invalid")
    _git(repo, "config", "user.name", "Lab")
    (repo / "f.txt").write_text("seed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")
    _git(repo, "checkout", "-qb", _BRANCH)
    (repo / "f.txt").write_text("reviewed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "the commit the operator reviewed")
    sha_a = _branch_head(repo, _BRANCH)

    # The gate resolves the branch through the State Store; the store is not the
    # subject here, so the binding is pinned and git is left real. BranchBinding
    # comes from approval_binding — approval_check imports only the FUNCTION, so
    # reaching for `approval_check.BranchBinding` yields None and the gate then
    # crashes on `binding.reason` instead of running.
    from atdd.coach.gate import approval_check as ac
    from atdd.coach.gate.approval_binding import BranchBinding

    monkeypatch.setattr(ac, "resolve_issue_branch",
                        lambda _start, _issue: BranchBinding(branch=_BRANCH))
    return repo, sha_a


def _mint_to_disk(repo, sha):
    """Write a real token at the path `approval_paths` resolves.

    Deliberately NOT in the fixture: until GREEN adds `head`, this raises
    TypeError, and a fixture that raises reports as a pytest ERROR whose message
    says nothing about the acceptance. Raised inside the test it is a FAILURE
    that names exactly what is missing.
    """
    from atdd.coach.gate.approval import approval_relpath, build_token

    token = build_token(_ISSUE, _FROM, _TO, approved_by="operator",
                        approved_at=_NOW, branch=_BRANCH, expires_at=_EXPIRES,
                        head=sha, key=_KEY)
    path = repo / approval_relpath(_ISSUE, _FROM, _TO)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token))
    return path


def _run_gate(repo):
    from atdd.coach.gate.approval_check import ApprovalTokenGateCheck
    from atdd.coach.gate.decision import GateContext

    check = ApprovalTokenGateCheck(signing_key=_KEY, now=_NOW)
    ctx = GateContext(issue_number=_ISSUE, from_phase=_FROM, to_phase=_TO,
                      worktree=str(repo))
    return check.run(ctx)


def test_the_gate_passes_at_the_approved_commit(repo_with_token):
    repo, sha_a = repo_with_token
    _mint_to_disk(repo, sha_a)

    result = _run_gate(repo)

    assert result.passed is True, (
        "the gate refuses the transition at the very commit the operator "
        f"approved; a binding that refuses its own commit is broken, not strict. "
        f"message: {result.message!r}"
    )


def test_the_gate_refuses_after_a_real_commit_lands(repo_with_token):
    """The token file is untouched. Only the branch moves."""
    from atdd.coach.gate.approval import approval_relpath

    repo, sha_a = repo_with_token
    _mint_to_disk(repo, sha_a)
    before = (repo / approval_relpath(_ISSUE, _FROM, _TO)).read_text()

    (repo / "f.txt").write_text("content the operator never saw\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "pushed after the approval")
    sha_b = _git(repo, "rev-parse", "HEAD")
    assert sha_b != sha_a

    after = (repo / approval_relpath(_ISSUE, _FROM, _TO)).read_text()
    assert after == before, "the lab modified the token; only the world may move"

    result = _run_gate(repo)

    assert result.passed is False, (
        f"the gate still authorises {_FROM}->{_TO} after the branch advanced from "
        f"{sha_a[:9]} to {sha_b[:9]}. The operator approved one diff and a "
        "different one is being merged under the same sign-off."
    )
    assert "content" in (result.message or "").lower() or "commit" in (result.message or "").lower(), (
        f"the gate refuses without naming the content change: {result.message!r}"
    )
