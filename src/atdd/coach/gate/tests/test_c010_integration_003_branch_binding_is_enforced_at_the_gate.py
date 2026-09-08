# URN: test:govern-lifecycle:operator-approval-token-gate:C010-INTEGRATION-003-branch-binding-is-enforced-at-the-gate
# Acceptance: acc:govern-lifecycle:C010-INTEGRATION-003-branch-binding-is-enforced-at-the-gate
# WMBT: wmbt:govern-lifecycle:C010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""C010-INTEGRATION-003 — the branch binding is ENFORCED, not merely recorded.

#1525 built branch binding into ``canonical_scope``/``sign_approval``/``verify_token``
and it was correct. Neither call site passed it, so it was inert: every token
verified on every branch, exactly as before the fix shipped. C010-UNIT-001 proves the
property in the pure module and C010-SMOKE-001 proves it in the shipped package —
both honestly noting they could not reach the gate. This file is the gate.

WHAT "ANOTHER BRANCH" MEANS HERE, and why it is not a test of where the command ran.
Both the mint and the check resolve the branch from the STATE STORE's issue binding,
never from ``git rev-parse`` in the current directory (see ``approval_binding`` for
why cwd would re-create the coupling #1376 removed). So the property under test is
drift over TIME, not over location: the token records the branch the issue was bound
to when the operator approved, and stops verifying once the issue is bound to a
different one. The last case below asserts the location-independence directly — the
same token, the same store, evaluated from a sibling worktree, still passes.

No fakes on either end: the real ``approve_command.run`` mints and the real
``ApprovalTokenGateCheck`` decides, against a real migrated State Store under an
isolated Control Root. Nothing is monkeypatched but the Control Root and the key.

RED state: ``approve_command`` calls ``build_token`` with no ``branch=`` and
``approval_check`` calls ``verify_token`` with no ``branch=``, so re-binding the issue
to another branch changes nothing and every assertion about refusal fails.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.gate.approve_command import run as run_approve
from atdd.coach.gate.approval_check import ApprovalTokenGateCheck
from atdd.coach.gate.approval_paths import approval_token_path
from atdd.coach.gate.decision import GateContext, GateVerdict
from atdd.state.smoke_evidence import open_state_store

pytestmark = [pytest.mark.platform]

# Never a live issue: the repo's issues are in the low thousands.
_ISSUE, _FROM, _TO = 999721, "PLANNED", "RED"
_UID = "token-binds-branch-and-expiry-integration-003"
_BRANCH_A = "feat/token-binds-branch-and-expiry"
_BRANCH_B = "feat/somebody-elses-work"
_KEY = "integration-operator-key"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated Control Root with the signing key pinned.

    ``ATDD_CONTROL_ROOT`` keeps every store read and write inside ``tmp_path``, so
    this can neither consult nor disturb the developer's real store — and no token
    joins the repository's live approval corpus.
    """
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    monkeypatch.setenv("ATDD_APPROVAL_SIGNING_KEY", _KEY)
    return tmp_path


def _bind(repo: Path, branch: str) -> None:
    """Bind the issue to ``branch`` in the store — what `atdd worktree create` writes."""
    with open_state_store(control_root=repo) as store:
        store.objects.upsert(_UID, "work_item", state=_FROM, data={"branch": branch})
        store.external_refs.link(_UID, "github", "issue", str(_ISSUE))


def _mint(repo: Path) -> int:
    return run_approve(
        [str(_ISSUE), "--transition", f"{_FROM}->{_TO}", "--by", "operator"],
        target_dir=repo,
        env={"USER": "operator"},
    )


def _check(worktree: Path):
    return ApprovalTokenGateCheck(signing_key=_KEY).run(
        GateContext(
            issue_number=_ISSUE, from_phase=_FROM, to_phase=_TO, worktree=worktree
        )
    )


def _token(repo: Path) -> dict:
    return json.loads(approval_token_path(repo, _ISSUE, _FROM, _TO).read_text())


def test_the_mint_records_the_branch_the_store_binds_the_issue_to(repo: Path) -> None:
    """The binding is on the artifact — the half #1525 shipped and nobody passed."""
    _bind(repo, _BRANCH_A)

    assert _mint(repo) == 0
    assert _token(repo)["branch"] == _BRANCH_A, (
        "the mint wrote a token with no branch binding; build_token accepts "
        "branch= and the call site is still not passing it"
    )


def test_the_token_passes_while_the_issue_is_still_bound_to_that_branch(repo: Path) -> None:
    """The guard discriminates rather than refusing everything."""
    _bind(repo, _BRANCH_A)
    assert _mint(repo) == 0

    result = _check(repo)

    assert result.passed is True, result.message
    assert _BRANCH_A in result.message, (
        f"a passing bound token should say what it is bound to; got {result.message!r}"
    )


def test_the_same_token_is_refused_once_the_issue_is_bound_elsewhere(repo: Path) -> None:
    """The property #1525 shipped, observable AT THE GATE for the first time."""
    _bind(repo, _BRANCH_A)
    assert _mint(repo) == 0
    before = _check(repo)
    assert before.passed is True, before.message

    # The issue moves: a rename, a recreated worktree, a re-pointed work item. The
    # token on disk is untouched — only what the issue is bound to has changed.
    _bind(repo, _BRANCH_B)

    after = _check(repo)

    assert after.passed is False, (
        "a token minted while the issue was bound to one branch still satisfied the "
        "gate after the issue was bound to another — the binding is recorded but "
        "not enforced, which is the whole of #1721"
    )
    assert after.verdict is GateVerdict.FAIL


def test_the_refusal_names_the_branch_change_and_not_a_signature_problem(repo: Path) -> None:
    """A gate that cannot say why it refused is the defect this program is named for.

    The token is intact here — correctly signed, correct issue, correct edge. Only
    the binding moved. Reporting that as "scope/signature mismatch" would send the
    operator looking for tampering instead of re-approving.
    """
    _bind(repo, _BRANCH_A)
    assert _mint(repo) == 0
    _bind(repo, _BRANCH_B)

    message = _check(repo).message

    assert "BRANCH CHANGED" in message, (
        f"the refusal does not name the branch change: {message!r}"
    )
    assert _BRANCH_A in message and _BRANCH_B in message, (
        f"the refusal must name BOTH branches for the operator to act on it: {message!r}"
    )
    assert "signature is invalid" not in message, (
        f"an intact token was reported as a signature problem: {message!r}"
    )


def test_the_verdict_does_not_depend_on_which_worktree_the_gate_ran_in(repo: Path) -> None:
    """The location-independence #1376 established, preserved by #1721.

    This is the assertion that would fail if the branch were read from
    ``git rev-parse --abbrev-ref HEAD``: the token's LOCATION became
    worktree-independent in #1376, and taking the branch from cwd would have made
    its VALIDITY worktree-dependent instead — the same defect wearing a different
    hat. Both worktrees resolve to the one Control Root, so both get one answer.
    """
    _bind(repo, _BRANCH_A)
    assert _mint(repo) == 0

    sibling = repo / "feat-another-worktree"
    sibling.mkdir()

    assert _check(sibling).passed is True, (
        "the same token, the same store binding, evaluated from a sibling worktree "
        "— a different verdict here means the branch is being read from the cwd"
    )
