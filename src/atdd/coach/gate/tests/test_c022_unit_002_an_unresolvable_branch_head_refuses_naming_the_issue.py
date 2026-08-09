# URN: test:govern-lifecycle:operator-approval-token-gate:C022-UNIT-002-an-unresolvable-branch-head-refuses-naming-the-issue
# Acceptance: acc:govern-lifecycle:C022-UNIT-002-an-unresolvable-branch-head-refuses-naming-the-issue
# WMBT: wmbt:govern-lifecycle:C022
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C022-UNIT-002 — refuse rather than fall back to the directory you are in.

#1765's second decision: *a mint that silently used the wrong tree is worse than
one that says it could not find the right one.* The obvious repair for "the
issue's branch head cannot be resolved here" is to use ``HEAD`` instead, and that
repair IS the defect — it is what the code did unconditionally, and it is why two
approvals were signed against a third branch's commit.

The refusal has to name the ISSUE and the BRANCH. An operator told "HEAD could
not be resolved in /some/path" cannot act on it: the thing to fix is a binding or
a missing branch, neither of which is a directory.

THE THREE INVARIANTS THIS REFUSAL IS EASIEST TO BREAK are asserted here beside
it, because a new blocking precondition is exactly the change that breaks them:

  - ``NOT_APPLICABLE`` must still PROCEED. #1670 measured that refusing it
    strands 787 of 787 work items behind ``--force``.
  - An empty registry must still be ``COULD_NOT_CHECK`` (#1619/#1632), and must
    still be decided BEFORE the head is asked for, so a resolution failure
    cannot displace the skip-count refusal that was the honest answer.
  - "Could not resolve" must stay distinguishable from "resolved to nothing" —
    ``resolve_issue_branch``'s discipline, which is why nothing here raises.

RED state: the mint resolves ``HEAD`` in the invoking directory and mints, so a
branch that exists nowhere is no obstacle at all.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from atdd.coach.gate.approval_paths import approval_token_path
from atdd.coach.gate.decision import GateCheckResult, GateContext, GateVerdict
from atdd.coach.gate.mint_gate import decide_mint, resolve_head
from atdd.coach.gate.registry import GateRegistry

pytestmark = [pytest.mark.platform]

_RULE = "repo.govern-lifecycle.c022"

#: Bound to a branch this repository does not have.
_DANGLING_ISSUE = 999123
_DANGLING_UID = "c022-unit-002-dangling-branch"
_DANGLING_BRANCH = "feat/a-branch-that-was-never-fetched-here"

#: Bound to a branch that does exist — the discriminating control, and the leg
#: that keeps NOT_APPLICABLE proceeding.
_LIVE_ISSUE = 999124
_LIVE_UID = "c022-unit-002-live-branch"
_LIVE_BRANCH = "feat/mint-resolves-head-from-the-issue-branch"

#: Registered, standing on the edge, but recording no branch at all.
_UNBOUND_ISSUE = 999125
_UNBOUND_UID = "c022-unit-002-no-branch-recorded"

#: Never registered in the store.
_UNKNOWN_ISSUE = 999126

_GIT_ID = ("-c", "user.name=t", "-c", "user.email=t@t")


@dataclass(frozen=True)
class _Scripted:
    """A substantive check whose verdict the test controls."""

    verdict: GateVerdict = GateVerdict.PASS
    gate_id: str = "GT-SUBSTANTIVE"
    rule_id: str = _RULE

    def run(self, ctx: GateContext) -> GateCheckResult:
        builder = {
            GateVerdict.PASS: GateCheckResult.passing,
            GateVerdict.NOT_APPLICABLE: GateCheckResult.not_applicable,
        }[self.verdict]
        return builder(self.gate_id, self.rule_id, f"scripted {self.verdict.value}")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *_GIT_ID, *args], cwd=cwd, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """A foreign worktree with a shared Control Root, as #1346/#1376 arrange one.

    The mint is invoked from ``foreign`` throughout, because that is where the
    question is live: from the issue's own directory a dangling binding would
    still be papered over by a ``HEAD`` that happened to answer.
    """
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))

    home = tmp_path / "issue-worktree"
    home.mkdir()
    _git(home, "init", "-q", "-b", _LIVE_BRANCH)
    _git(home, "commit", "-q", "--allow-empty", "-m", "the issue's work")
    live_head = _git(home, "rev-parse", "HEAD")

    foreign = tmp_path / "foreign-worktree"
    _git(home, "worktree", "add", "-q", "-b", "feat/token-proves-gates-passed",
         str(foreign))
    _git(foreign, "commit", "-q", "--allow-empty", "-m", "somebody else's work")
    foreign_head = _git(foreign, "rev-parse", "HEAD")

    for root in (home, foreign):
        (root / ".atdd").mkdir(parents=True, exist_ok=True)
        (root / ".atdd" / "config.yaml").write_text(
            "gate:\n  transitions:\n    SMOKE->REFACTOR: true\n"
        )

    _seed(tmp_path)
    return {"home": home, "foreign": foreign,
            "live_head": live_head, "foreign_head": foreign_head}


def _seed(control_root: Path) -> None:
    """Three real work items: one bound to a live branch, one dangling, one bare."""
    from atdd.state.smoke_evidence import open_state_store

    with open_state_store(control_root=control_root) as store:
        for uid, issue, data in (
            (_LIVE_UID, _LIVE_ISSUE, {"branch": _LIVE_BRANCH}),
            (_DANGLING_UID, _DANGLING_ISSUE, {"branch": _DANGLING_BRANCH}),
            (_UNBOUND_UID, _UNBOUND_ISSUE, {}),
        ):
            store.objects.upsert(uid, "work_item", state="SMOKE", data=data)
            store.external_refs.link(uid, "github", "issue", str(issue))


def _decide(worktree: Path, issue: int, *,
            verdict: GateVerdict = GateVerdict.PASS,
            registry: GateRegistry | None = None):
    if registry is None:
        registry = GateRegistry()
        registry.register("SMOKE", "REFACTOR", _Scripted(verdict))
    return decide_mint(
        worktree, issue, "SMOKE", "REFACTOR", registry=registry, registrars=()
    )


def test_a_branch_head_that_does_not_resolve_refuses(repo):
    """No fallback. The check would have passed; the mint refuses anyway."""
    decision = _decide(repo["foreign"], _DANGLING_ISSUE)

    assert decision.proceed is False, (
        "the mint signed an approval for an issue whose branch head it could not "
        "find — the only commit available to it was the invoking directory's, "
        "which is the tree #1765 exists to stop it certifying"
    )
    assert decision.verdict is GateVerdict.COULD_NOT_CHECK, (
        "an unresolvable branch head is an unmade observation, not an observed "
        "violation; the operator's remedy is to fix a binding, not to fix code"
    )
    assert decision.head is None


def test_the_refusal_names_the_issue_and_the_branch_not_a_directory(repo):
    """An operator told about a path cannot fix a binding."""
    rendered = _decide(repo["foreign"], _DANGLING_ISSUE).render()

    assert f"#{_DANGLING_ISSUE}" in rendered, (
        f"the refusal does not name the issue it is about:\n{rendered}"
    )
    assert _DANGLING_BRANCH in rendered, (
        f"the refusal does not name the branch that could not be resolved:\n{rendered}"
    )
    assert repo["foreign_head"] not in rendered, (
        "the refusal quoted the invoking worktree's commit, which is the one "
        "value that is certainly not the answer"
    )


def test_no_token_is_written_when_the_head_cannot_be_resolved(repo, monkeypatch):
    """Same rule as every other refusal: the absence of the artifact IS the refusal."""
    from atdd.coach.gate import approve_command, mint_gate

    registry = GateRegistry()
    registry.register("SMOKE", "REFACTOR", _Scripted())
    monkeypatch.setattr(mint_gate, "GATE_REGISTRY", registry)
    monkeypatch.setattr(mint_gate, "DEFAULT_REGISTRARS", ())

    rc = approve_command.run(
        [str(_DANGLING_ISSUE), "--transition", "SMOKE->REFACTOR"],
        target_dir=repo["foreign"], env={},
    )

    assert rc != 0
    assert not approval_token_path(
        repo["foreign"], _DANGLING_ISSUE, "SMOKE", "REFACTOR"
    ).exists()


def test_an_empty_binding_is_reported_rather_than_raised(repo):
    """Three empty answers, three reasons, no exception — #1721's discipline.

    ``decision.run_checks`` flattens a raised exception into ``FAIL``, which
    would report an unreadable store as an observed violation. So the resolution
    reports instead, and the two shapes of nothing keep their own reasons.
    """
    unbound = resolve_head(repo["foreign"], _UNBOUND_ISSUE)
    unknown = resolve_head(repo["foreign"], _UNKNOWN_ISSUE)
    dangling = resolve_head(repo["foreign"], _DANGLING_ISSUE)

    assert not unbound and not unknown and not dangling
    assert "records no branch" in unbound.reason
    assert "no work item" in unknown.reason
    assert _DANGLING_BRANCH in dangling.reason
    assert dangling.branch == _DANGLING_BRANCH, (
        "the branch that WAS found is dropped, so the refusal cannot name it"
    )
    for issue in (_UNBOUND_ISSUE, _UNKNOWN_ISSUE):
        assert _decide(repo["foreign"], issue).verdict is GateVerdict.COULD_NOT_CHECK


def test_not_applicable_still_proceeds_from_a_foreign_worktree(repo):
    """The safety property #1670 measured at 787 of 787, re-asserted under #1765.

    A new blocking precondition ahead of the gate run is precisely the change
    that strands every issue owing no live smoke. It must not, and it must not
    do so from a sibling worktree either.
    """
    decision = _decide(repo["foreign"], _LIVE_ISSUE, verdict=GateVerdict.NOT_APPLICABLE)

    assert decision.proceed is True, (
        "the mint refused an issue that owes no live smoke — this strands every "
        "issue declaring no live_smoke acceptance at SMOKE behind --force"
    )
    assert decision.coverage.verified == 0
    assert decision.coverage.none_owed == 1
    assert decision.head == repo["live_head"]


def test_an_empty_registry_is_still_could_not_check_and_still_decided_first(repo):
    """The skip-count refusal must not be displaced by a resolution failure.

    Asserted on the DANGLING issue: both refusals apply, and the honest one is
    the empty registry — nothing was observed, which is a different fact from
    the tree being unnameable, and #1632's rule is the one the operator needs.
    """
    decision = _decide(repo["foreign"], _DANGLING_ISSUE, registry=GateRegistry())

    assert decision.proceed is False
    assert decision.verdict is GateVerdict.COULD_NOT_CHECK
    assert "no substantive gate check was evaluated" in decision.reason, (
        f"the empty-registry refusal was displaced by the head resolution:\n"
        f"{decision.render()}"
    )
