# URN: test:govern-lifecycle:worktree-name-is-a-valid-refname:Y009-SMOKE-001-a-real-unverified-record-gets-a-worktree
# Acceptance: acc:govern-lifecycle:Y009-SMOKE-001-a-real-unverified-record-gets-a-worktree
# WMBT: wmbt:govern-lifecycle:Y009
# Phase: SMOKE
# Layer: integration
"""Y009-SMOKE-001 — a real store record with an `unverified:` uid gets a worktree (#1913).

The UNIT test checks the sanitizer against `git check-ref-format`. This one is the
operator's path: a real State Store holding a work item whose uid is
``unverified:<slug>``, a real git repository, and `WorktreeManager.create` — the
function `atdd worktree create` dispatches to — producing a real branch and a real
worktree directory.

That distinction is the whole issue. The sanitizer being correct proves nothing
about `atdd worktree create`, because the slug is read from the store two lines
before the branch name is built, and the failure lives in that join. Before this
change the call ended in `git worktree add failed` with no further information;
here it must end in a branch that exists.
"""
from __future__ import annotations

import pathlib
import subprocess

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore

pytestmark = [pytest.mark.platform]

ISSUE = 8140
UNVERIFIED_UID = "unverified:stale-version-cache-advertises-phantom-upgrade"
EXPECTED_BRANCH = "fix/stale-version-cache-advertises-phantom-upgrade"


def _git(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)


@pytest.fixture()
def repo_with_unverified_record(tmp_path: pathlib.Path) -> pathlib.Path:
    """A real repo whose store holds exactly the record shape that failed."""
    repo = tmp_path / "main"
    repo.mkdir(parents=True)
    (repo / ".atdd").mkdir()
    (repo / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")

    _git(repo, "init", "-q", "-b", "main", ".")
    _git(repo, "config", "user.email", "y009@example.invalid")
    _git(repo, "config", "user.name", "Y009")
    _git(repo, "config", "core.hooksPath", "/dev/null")
    (repo / "README.md").write_text("y009\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")

    # The create path bases the new worktree on `origin/<default>`, so a real
    # bare remote is part of the subject, not scaffolding around it.
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", "-b", "main", str(origin)], check=True)
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "origin", "main")
    _git(repo, "fetch", "-q", "origin")

    store = StateStore(connect(init_state_store(start=repo)))
    store.objects.upsert(UNVERIFIED_UID, WORK_ITEM_KIND, state="INIT",
                         data={"issue_number": ISSUE, "type": "bug"})
    store.external_refs.link(UNVERIFIED_UID, GITHUB_PROVIDER, "issue", str(ISSUE))
    return repo


def test_the_store_really_hands_back_the_unverified_uid_as_the_slug(
    repo_with_unverified_record,
) -> None:
    """Guards the guard.

    If the fixture stopped producing an `unverified:` slug the test below would
    pass over an ordinary record and prove nothing about the defect.
    """
    from atdd.coach.commands.branch import _store_session_entry

    entry = _store_session_entry(repo_with_unverified_record, ISSUE)
    assert entry is not None, "the seeded record is not resolvable by issue number"
    assert entry["slug"] == UNVERIFIED_UID, (
        f"expected the raw uid as the slug, got {entry['slug']!r}"
    )


def test_a_worktree_is_created_and_the_branch_is_valid(
    repo_with_unverified_record,
) -> None:
    """THE POINT: this ended in `git worktree add failed` for 633 of 822 records."""
    from atdd.coach.commands.branch import BranchManager

    rc = BranchManager(repo_with_unverified_record).branch(ISSUE, prefix="fix")
    assert rc == 0, "worktree create refused a record it should now handle"

    branches = _git(repo_with_unverified_record, "branch", "--list").stdout
    assert EXPECTED_BRANCH in branches, (
        f"expected {EXPECTED_BRANCH!r} among:\n{branches}"
    )
    assert ":" not in branches, f"a colon reached a refname:\n{branches}"

    listed = _git(repo_with_unverified_record, "worktree", "list").stdout
    assert "stale-version-cache-advertises-phantom-upgrade" in listed, listed


def test_the_provenance_qualifier_does_not_reach_the_branch_name(
    repo_with_unverified_record,
) -> None:
    """`unverified:` is a statement about the record, not part of the work's name."""
    from atdd.coach.commands.branch import BranchManager

    BranchManager(repo_with_unverified_record).branch(ISSUE, prefix="fix")
    branches = _git(repo_with_unverified_record, "branch", "--list").stdout
    assert "unverified" not in branches, branches
