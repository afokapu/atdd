# URN: test:govern-lifecycle:operator-approval-token-gate:C022-SMOKE-001-the-real-command-signs-for-the-issues-tree-from-a-foreign-worktree
# Acceptance: acc:govern-lifecycle:C022-SMOKE-001-the-real-command-signs-for-the-issues-tree-from-a-foreign-worktree
# WMBT: wmbt:govern-lifecycle:C022
# Phase: SMOKE
# Layer: smoke
# Assertion: behavioral
"""C022-SMOKE-001 — the SHIPPED command, from the wrong directory, in a real process.

The two bad approvals were not produced by a harness. They were produced by
``atdd coach approve``, run by an operator standing in a third worktree, and the
only reason nobody was misled is that ``SmokeExecutionGateCheck`` happened to owe
nothing for either issue. So the subject here is the artifact an operator runs:
a SEPARATE REAL PROCESS, the real CLI entry point, the real registrars, the real
``SmokeExecutionGateCheck``, a real git repository with a real linked worktree,
and a real migrated State Store. No in-process import of the command, no
monkeypatching, no fakes.

The reproduction from the issue, exactly::

    cd <any worktree that is NOT the issue's>
    atdd coach approve <N> --transition 'SMOKE->REFACTOR'
    # compare the printed sha against: git -C <the issue's worktree> rev-parse HEAD

ASSERTED AGAINST THE REPOSITORY, NOT AGAINST A LITERAL. Both heads are read back
out of the real repo with ``git`` and asserted to differ before anything else, so
the comparison cannot pass by agreeing with itself and cannot degenerate into a
tautology if the fixture ever puts both branches on one commit.

The source tree goes first on PYTHONPATH because the ambient interpreter also has
a published atdd wheel installed, and a smoke that silently imported the released
package would prove nothing about this change. Everything runs under a temp
Control Root, so no live issue is touched and no token joins the repository's real
approval corpus.

RED state: the shipped command prints the head of the worktree it was invoked
from, so the printed sha equals ``foreign_head`` and the assertion on the issue's
own head fails.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from atdd.coach.gate.approval import approval_relpath
from atdd.state.smoke_evidence import open_state_store

pytestmark = [pytest.mark.platform, pytest.mark.smoke]

# Never a live issue: the repo's issues are in the low thousands.
_ISSUE, _FROM, _TO = 999765, "SMOKE", "REFACTOR"
_UID = "c022-smoke-001-real-command-from-a-foreign-worktree"

#: The branch the store binds the issue to — whose head must be certified.
_ISSUE_BRANCH = "feat/mint-resolves-head-from-the-issue-branch"

#: Where the operator is standing. Named after the directory that produced the
#: two bad approvals on 2026-08-08, because that is what it was.
_FOREIGN_BRANCH = "feat/token-proves-gates-passed"

_GIT_ID = ("-c", "user.name=t", "-c", "user.email=t@t")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *_GIT_ID, *args], cwd=cwd, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def _env(root: Path) -> dict:
    """Ambient env, the source tree first on PYTHONPATH, pinned to the temp root."""
    src_root = Path(__file__).resolve().parents[4]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root) + os.pathsep + env.get("PYTHONPATH", "")
    env["ATDD_APPROVAL_SIGNING_KEY"] = "smoke-operator-key"
    env["ATDD_CONTROL_ROOT"] = str(root)
    return env


@pytest.fixture
def repo(tmp_path: Path) -> dict:
    """Two real worktrees of one real repository, on two commits, one Control Root.

    ``SMOKE->REFACTOR`` is gated in both ``.atdd/config.yaml`` files because the
    mint reads gatedness where it was invoked; the shared Control Root is what
    makes the branch binding readable from either, which is #1346/#1376's
    arrangement and the one the defect was measured in.

    The work item declares no ``execution_kind: live_smoke`` acceptance, so the
    real ``SmokeExecutionGateCheck`` reports NOT_APPLICABLE and the mint proceeds
    — the same state #1671 and #1653 were in when they printed the wrong commit,
    and the state 787 of 787 work items are in.
    """
    home = tmp_path / "issue-worktree"
    home.mkdir()
    _git(home, "init", "-q", "-b", _ISSUE_BRANCH)
    _git(home, "commit", "-q", "--allow-empty", "-m", "the issue's work")

    foreign = tmp_path / "foreign-worktree"
    _git(home, "worktree", "add", "-q", "-b", _FOREIGN_BRANCH, str(foreign))
    _git(foreign, "commit", "-q", "--allow-empty", "-m", "somebody else's work")

    for root in (home, foreign):
        (root / ".atdd").mkdir(parents=True, exist_ok=True)
        (root / ".atdd" / "config.yaml").write_text(
            "gate:\n  transitions:\n    SMOKE->REFACTOR: true\n"
        )

    (tmp_path / ".atdd" / "state").mkdir(parents=True, exist_ok=True)
    with open_state_store(control_root=tmp_path) as store:
        store.objects.upsert(
            _UID, "work_item", state=_FROM, data={"branch": _ISSUE_BRANCH}
        )
        store.external_refs.link(_UID, "github", "issue", str(_ISSUE))

    issue_head = _git(home, "rev-parse", "HEAD")
    foreign_head = _git(foreign, "rev-parse", "HEAD")
    assert issue_head != foreign_head, (
        "the fixture put both worktrees on one commit, so the comparison below "
        "would hold no matter which head the command used"
    )
    return {"root": tmp_path, "home": home, "foreign": foreign,
            "issue_head": issue_head, "foreign_head": foreign_head}


def _approve_from(repo: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "atdd.cli", "coach", "approve",
         str(_ISSUE), "--transition", f"{_FROM}->{_TO}"],
        capture_output=True, text=True, timeout=180,
        cwd=str(cwd), env=_env(repo["root"]),
    )


def test_the_shipped_command_names_the_issues_commit_from_a_foreign_worktree(repo):
    """The 2026-08-08 reproduction, against the binary an operator actually invokes."""
    approved = _approve_from(repo, repo["foreign"])

    assert approved.returncode == 0, (
        f"the shipped command refused from a sibling worktree; "
        f"stdout:\n{approved.stdout[-1200:]}\nstderr:\n{approved.stderr[-1200:]}"
    )
    assert repo["issue_head"][:12] in approved.stdout, (
        f"the shipped command did not name the head of {_ISSUE_BRANCH} "
        f"({repo['issue_head'][:12]}); stdout:\n{approved.stdout[-1200:]}"
    )
    assert repo["foreign_head"][:12] not in approved.stdout, (
        f"the shipped command named the head of the directory it was invoked "
        f"from ({repo['foreign_head'][:12]}) — the exact output #1671 and #1653 "
        f"produced; stdout:\n{approved.stdout[-1200:]}"
    )


def test_the_token_is_bound_to_the_branch_whose_head_was_printed(repo):
    """The mint's two claims must agree in the artifact, not only in the process.

    The observed output was internally inconsistent: the token bound to the
    issue's branch, the certified commit belonging to another. This reads the
    token off disk and compares it against what the same run printed.
    """
    approved = _approve_from(repo, repo["foreign"])
    token_path = repo["root"] / approval_relpath(_ISSUE, _FROM, _TO)

    assert token_path.exists(), (
        f"the shipped command reported success and wrote no token; "
        f"stdout:\n{approved.stdout[-1200:]}"
    )
    token = json.loads(token_path.read_text())

    assert token["branch"] == _ISSUE_BRANCH
    assert token["branch"] in approved.stdout, (
        "the certified commit is printed without the branch it belongs to, so "
        "the inconsistency that produced #1765 stays invisible in the output"
    )
    assert repo["issue_head"] == _git(
        repo["foreign"], "rev-parse", f"refs/heads/{token['branch']}"
    )


def test_the_issues_own_worktree_prints_the_same_commit(repo):
    """The no-regression leg: the answer is a property of the issue, not the cwd.

    Also the discriminating control — without it, a command that printed some
    fixed unrelated string would satisfy both assertions above.
    """
    from_home = _approve_from(repo, repo["home"])

    assert from_home.returncode == 0, (
        f"the shipped command refused from the issue's own worktree; "
        f"stdout:\n{from_home.stdout[-1200:]}\nstderr:\n{from_home.stderr[-1200:]}"
    )
    assert repo["issue_head"][:12] in from_home.stdout
    assert _git(repo["home"], "rev-parse", "HEAD") == repo["issue_head"]
