# URN: test:govern-lifecycle:operator-approval-token-gate:C022-UNIT-001-the-mint-names-the-issues-branch-head-not-the-invoking-worktrees
# Acceptance: acc:govern-lifecycle:C022-UNIT-001-the-mint-names-the-issues-branch-head-not-the-invoking-worktrees
# WMBT: wmbt:govern-lifecycle:C022
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C022-UNIT-001 — the mint certifies the ISSUE's tree, not the operator's.

``resolve_issue_head(worktree)`` shelled ``git rev-parse HEAD`` in the directory the
mint was invoked from. Measured 2026-08-08 on the first two issues to cross
``SMOKE->REFACTOR`` after #1670 slice C merged::

    #1671:  SMOKE->REFACTOR: gates evaluated for #1671 at a24b3e237007
    #1653:  SMOKE->REFACTOR: gates evaluated for #1653 at a24b3e237007

    a24b3e237007  = HEAD of feat-token-proves-gates-passed   <- the operator's cwd
    237d727e5a37  = HEAD of #1671's branch
    d7a53da439c4  = HEAD of #1653's branch

Neither issue's commit was used. Both were evaluated against a THIRD branch's
head, and the token was correctly bound to each issue's own branch by #1721 — so
the mint named one branch and attested a commit from another.

THE SHAPE OF THIS FILE IS THE POINT. The bug is invisible from the issue's own
worktree, where the two answers coincide; every existing mint test ran there. So
the arrangement here is two branches at two DIFFERENT commits, with the mint
invoked from the one the issue is not bound to, and the control leg re-runs the
same decision from the issue's own worktree to prove the fix removed a dependency
on the operator's location rather than adding one.

RED state: ``decide_mint`` reports the invoking worktree's HEAD, so
``test_the_commit_is_the_issues_branch_head`` fails on the sha it names.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from atdd.coach.gate.approval_binding import resolve_issue_branch
from atdd.coach.gate.decision import GateCheckResult, GateContext, GateVerdict
from atdd.coach.gate.mint_gate import decide_mint
from atdd.coach.gate.registry import GateRegistry

pytestmark = [pytest.mark.platform]

_RULE = "repo.govern-lifecycle.c022"
_ISSUE = 999122
_UID = "c022-unit-001-issue-branch-head"

#: The branch the store binds the issue to — the one whose head must be certified.
_ISSUE_BRANCH = "feat/mint-resolves-head-from-the-issue-branch"

#: The branch the operator happens to be standing on. Named after the directory
#: that actually produced the two bad approvals, because that is what it was.
_FOREIGN_BRANCH = "feat/token-proves-gates-passed"

_GIT_ID = ("-c", "user.name=t", "-c", "user.email=t@t")


@dataclass(frozen=True)
class _AlwaysPasses:
    """A substantive check, so the mint reaches the decision under test."""

    gate_id: str = "GT-SUBSTANTIVE"
    rule_id: str = _RULE

    def run(self, ctx: GateContext) -> GateCheckResult:
        return GateCheckResult.passing(self.gate_id, self.rule_id, "observed, satisfied")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *_GIT_ID, *args], cwd=cwd, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def _gate_config(root: Path) -> None:
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    (root / ".atdd" / "config.yaml").write_text(
        "gate:\n  transitions:\n    SMOKE->REFACTOR: true\n"
    )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """One repository, two branches, two DIFFERENT commits, two worktrees.

    A LINKED WORKTREE, not a second clone, because that is the arrangement the
    defect was measured in and the one that makes the fix work: worktrees of a
    repository share a single ``refs/`` namespace, so ``refs/heads/<branch>``
    answers the same commit from either directory while ``HEAD`` answers a
    different one in each. A second clone would not exercise that.

    ONE Control Root for both, which is #1346's arrangement and #1376's whole
    point: the store the branch binding is read from is shared, so the two
    directories differ in exactly one respect — their ``HEAD``. Giving each its
    own store would hide the defect behind a second difference.

    Both directories get their own ``.atdd/config.yaml`` gating the edge, since
    the mint reads its gatedness where it was invoked.
    """
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))

    home = tmp_path / "issue-worktree"
    home.mkdir()
    _git(home, "init", "-q", "-b", _ISSUE_BRANCH)
    _git(home, "commit", "-q", "--allow-empty", "-m", "the issue's work")
    issue_head = _git(home, "rev-parse", "HEAD")

    foreign = tmp_path / "foreign-worktree"
    _git(home, "worktree", "add", "-q", "-b", _FOREIGN_BRANCH, str(foreign))
    _git(foreign, "commit", "-q", "--allow-empty", "-m", "somebody else's work")
    foreign_head = _git(foreign, "rev-parse", "HEAD")

    assert issue_head != foreign_head, (
        "the fixture put both branches on one commit, so nothing below could "
        "tell the issue's head from the operator's"
    )

    _gate_config(home)
    _gate_config(foreign)
    _bind_issue(tmp_path)
    return {"home": home, "foreign": foreign,
            "issue_head": issue_head, "foreign_head": foreign_head}


def _bind_issue(root: Path) -> None:
    """Seed the State Store binding — real state, the way #1721 requires it.

    This is the edge the fix resolves through, so it is also the fixture's
    subject: the work item records ``branch``, exactly as ``atdd worktree
    create`` writes it, and the mint is expected to follow it to a commit.
    """
    from atdd.state.smoke_evidence import open_state_store

    with open_state_store(control_root=root) as store:
        store.objects.upsert(
            _UID, "work_item", state="SMOKE", data={"branch": _ISSUE_BRANCH}
        )
        store.external_refs.link(_UID, "github", "issue", str(_ISSUE))


def _decide(worktree: Path):
    registry = GateRegistry()
    registry.register("SMOKE", "REFACTOR", _AlwaysPasses())
    return decide_mint(
        worktree, _ISSUE, "SMOKE", "REFACTOR", registry=registry, registrars=()
    )


def test_the_commit_is_the_issues_branch_head(repo):
    """The defect, stated as one comparison."""
    decision = _decide(repo["foreign"])

    assert decision.proceed is True, (
        f"the mint refused from a sibling worktree: {decision.render()}"
    )
    assert decision.head == repo["issue_head"], (
        "the mint certified a commit that is not the head of the branch this "
        "issue is bound to — which is how two approvals came to be signed "
        "against a third branch's commit on 2026-08-08"
    )


def test_the_commit_is_not_the_invoking_worktrees_head(repo):
    """The other half of the same fact, so neither side can absorb the other.

    Asserted separately because a mint that resolved nothing and reported an
    empty sha would satisfy the inequality on its own; the leg above pins the
    value and this one pins what it must not be.
    """
    decision = _decide(repo["foreign"])

    assert decision.head != repo["foreign_head"], (
        "the commit certified is the HEAD of the directory the mint was invoked "
        "from — the operator's location is being used as a proxy for the issue's "
        "tree, which is the whole defect"
    )
    assert repo["foreign_head"] not in decision.render(), (
        "the operator-facing text still names the invoking worktree's commit"
    )


def test_the_report_names_the_commit_and_the_branch_together(repo):
    """A bare sha is unfalsifiable to the operator reading it.

    The observed output named one branch (in the token binding) and attested
    another branch's commit (in this line), and the inconsistency was only
    findable by running ``rev-parse`` in three worktrees. Printed together, a
    repeat is legible in the line itself.
    """
    rendered = _decide(repo["foreign"]).render()

    assert repo["issue_head"][:12] in rendered, (
        f"the report does not name the commit it certified:\n{rendered}"
    )
    assert _ISSUE_BRANCH in rendered, (
        f"the report names a commit without the branch it belongs to:\n{rendered}"
    )


def test_the_issues_own_worktree_is_unchanged(repo):
    """No regression: the fix removes a dependency on location, not adds one.

    From the issue's own directory the old code and the new code agree, and that
    has to stay true — this is the invocation every existing mint test makes and
    the one an operator standing in the right place makes.
    """
    from_home = _decide(repo["home"])
    from_foreign = _decide(repo["foreign"])

    assert from_home.proceed is True
    assert from_home.head == repo["issue_head"] == _git(repo["home"], "rev-parse", "HEAD")
    assert from_home.head == from_foreign.head, (
        "the mint still answers differently depending on where it was run"
    )
    assert from_home.verdict is from_foreign.verdict


def test_the_certified_commit_belongs_to_the_branch_the_token_binds(repo):
    """The mint's two claims must agree.

    #1721 binds the token to ``resolve_issue_branch``'s answer and #1765 binds
    the certified commit to the head of that same branch. Asserting them against
    each other — rather than each against a literal — is what makes 'the output
    cannot name a commit belonging to another branch' a property rather than a
    coincidence of this fixture.
    """
    decision = _decide(repo["foreign"])
    binding = resolve_issue_branch(repo["foreign"], _ISSUE)

    assert binding.branch == decision.branch, (
        "the token would be bound to one branch while the gates were certified "
        "for another — the internal inconsistency #1765 was filed for"
    )
    assert decision.head == _git(
        repo["foreign"], "rev-parse", f"refs/heads/{binding.branch}"
    )
    assert decision.verdict is GateVerdict.PASS
