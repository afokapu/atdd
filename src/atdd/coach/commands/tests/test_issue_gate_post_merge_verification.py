"""The COMPLETE gate must be satisfiable after the merge, not only before it (#1611).

``atdd auto-phase`` runs on ``pull_request: closed``, and the runner checks out
``main`` at the commit the merge produced. Two of the COMPLETE gates asked
questions that are false by construction at that moment:

- a declared **modified** artifact was checked with ``git diff main...HEAD``, and
  once the branch is merged ``main`` *is* ``HEAD``, so that symmetric difference is
  empty for every path the branch touched;
- the rebase gate demanded ``origin/main`` be an ancestor of ``HEAD``, which stops
  being true the moment any other PR merges after this one.

Both then printed ``--force`` as the only exit, which turns a fail-closed gate into
a rubber stamp. The fix is to ask what the PR *landed*: the commit that carried the
issue's work into main, and its first parent.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.issue import IssueManager

ISSUE = 1611


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


@pytest.fixture()
def merged_repo(tmp_path: Path) -> Path:
    """A repo in the state auto-phase sees: on ``main``, at the commit the PR landed.

    The shape mirrors the live runs — a squash merge, so the landed commit has one
    parent and ``git diff main...HEAD`` is empty.
    """
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "--initial-branch=main")

    repo = tmp_path / "work"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.email", "gate@example.test")
    _git(repo, "config", "user.name", "Gate Test")
    _git(repo, "remote", "add", "origin", str(origin))

    (repo / "tracked.py").write_text("original\n")
    (repo / "doomed.py").write_text("goes away\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    _git(repo, "push", "-u", "origin", "main")

    _git(repo, "checkout", "-b", "feat/work")
    (repo / "tracked.py").write_text("changed by the PR\n")
    (repo / "created.py").write_text("new\n")
    (repo / "doomed.py").unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "the PR's work")

    # The merge, as GitHub performs it for this repo: squashed onto main.
    _git(repo, "checkout", "main")
    _git(repo, "merge", "--squash", "feat/work")
    _git(repo, "commit", "-m", "the PR's work (#1611) (#9999)")
    _git(repo, "push", "origin", "main")
    _git(repo, "branch", "-D", "feat/work")
    return repo


def _manager(repo: Path, landed: str | None) -> IssueManager:
    manager = IssueManager(target_dir=repo)
    manager._landed_commit = lambda issue_number: landed  # type: ignore[method-assign]
    return manager


def test_modified_artifact_verifies_against_what_the_pr_landed(merged_repo: Path) -> None:
    """Post-merge, a declared modification is checked against the landed commit."""
    landed = _git(merged_repo, "rev-parse", "HEAD")

    # The premise: the old question is empty by construction here.
    assert _git(merged_repo, "diff", "main...HEAD", "--", "tracked.py") == ""

    manager = _manager(merged_repo, landed)
    valid, messages = manager._verify_artifacts(
        {"created": ["created.py"], "modified": ["tracked.py"], "deleted": ["doomed.py"]},
        issue_number=ISSUE,
    )
    assert valid, "\n".join(messages)
    assert any("tracked.py" in m and "CHANGED" in m for m in messages), messages
    assert any("created.py" in m and "EXISTS" in m for m in messages), messages
    assert any("doomed.py" in m and "CONFIRMED GONE" in m for m in messages), messages


def test_a_modification_the_pr_did_not_make_still_fails(merged_repo: Path) -> None:
    """The gate still refuses a claim the landed commit does not support."""
    landed = _git(merged_repo, "rev-parse", "HEAD")
    (merged_repo / "untouched.py").write_text("not part of the PR\n")
    _git(merged_repo, "add", "-A")
    _git(merged_repo, "commit", "-m", "a later, unrelated commit")

    manager = _manager(merged_repo, landed)
    valid, messages = manager._verify_artifacts(
        {"created": [], "modified": ["untouched.py"], "deleted": []},
        issue_number=ISSUE,
    )
    assert not valid, messages
    assert any("untouched.py" in m and "NO CHANGES" in m for m in messages), messages


def test_pre_merge_still_compares_the_branch_against_main(merged_repo: Path) -> None:
    """With no landed commit to point at, the branch-vs-main question is kept."""
    _git(merged_repo, "checkout", "-b", "feat/next")
    (merged_repo / "tracked.py").write_text("changed again, not yet merged\n")
    _git(merged_repo, "add", "-A")
    _git(merged_repo, "commit", "-m", "work in progress")

    manager = _manager(merged_repo, None)
    valid, messages = manager._verify_artifacts(
        {"created": [], "modified": ["tracked.py"], "deleted": []},
        issue_number=ISSUE,
    )
    assert valid, "\n".join(messages)


@pytest.mark.parametrize(
    "bullet, expected",
    [
        ("- `src/atdd/cli.py` (`_substrate_root`)", "src/atdd/cli.py"),
        ("- `src/atdd/cli.py` — why it changed", "src/atdd/cli.py"),
        ("- `src/atdd/cli.py` - why it changed", "src/atdd/cli.py"),
        ("- `src/atdd/cli.py`", "src/atdd/cli.py"),
        ("- src/atdd/cli.py (a note)", "src/atdd/cli.py"),
        ("- (the artifact this issue lands)", None),
    ],
)
def test_artifact_path_survives_an_annotated_bullet(bullet: str, expected) -> None:
    """A backticked path with a note after it is still that path.

    The bullets are Markdown, and the template invites a note: ``- `path` (why)``.
    The closing backtick was stripped before the note was, so the note took the
    backtick's place in the string and every annotated path became a path that no
    revision could contain — ``src/atdd/cli.py```. #1601 declared exactly that.
    """
    assert IssueManager._artifact_path(bullet) == expected


def test_rebase_gate_accepts_work_already_contained_in_main(merged_repo: Path) -> None:
    """Main moving on after the merge is not this branch being behind."""
    landed = _git(merged_repo, "rev-parse", "HEAD")

    # Another PR merges after ours, so origin/main is ahead of the checkout.
    (merged_repo / "someone_else.py").write_text("a later merge\n")
    _git(merged_repo, "add", "-A")
    _git(merged_repo, "commit", "-m", "somebody else's PR")
    _git(merged_repo, "push", "origin", "main")
    _git(merged_repo, "reset", "--hard", landed)

    manager = IssueManager(target_dir=merged_repo)
    passed, message = manager._check_rebased_on_main()
    assert passed, message


def test_rebase_gate_still_refuses_a_branch_that_is_genuinely_behind(
    merged_repo: Path,
) -> None:
    """A branch with unmerged work on a stale base is still refused."""
    landed = _git(merged_repo, "rev-parse", "HEAD")
    (merged_repo / "someone_else.py").write_text("a later merge\n")
    _git(merged_repo, "add", "-A")
    _git(merged_repo, "commit", "-m", "somebody else's PR")
    _git(merged_repo, "push", "origin", "main")

    _git(merged_repo, "checkout", "-b", "feat/stale", landed)
    (merged_repo / "mine.py").write_text("unmerged work on a stale base\n")
    _git(merged_repo, "add", "-A")
    _git(merged_repo, "commit", "-m", "my work")

    manager = IssueManager(target_dir=merged_repo)
    passed, message = manager._check_rebased_on_main()
    assert not passed, message
