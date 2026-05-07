"""Fixture lock for the empty-branch PR-deferral contract (issue #478).

`atdd branch <N>` MUST NOT call `gh pr create` when the branch has 0 commits
past the resolved default branch — GitHub's createPullRequest mutation hard-
fails when head==base, and that failure looks like a real error to users.

Three fixtures cover:
  (a) empty branch produces a structured hint and never invokes `gh pr create`
  (b) non-empty branch still attempts PR creation (deferral does not regress
      the happy path)
  (c) `atdd pr <N>` on an empty branch exits non-zero with a #467-shaped Fix
      hint, never invoking `gh pr create`

Run: PYTHONPATH=src python3 -m pytest -q \\
     src/atdd/coach/commands/tests/test_branch_empty_pr_defer.py -v
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.commands.branch import BranchManager
from atdd.coach.commands.pr import PRManager


pytestmark = [pytest.mark.platform]


def _completed(returncode: int = 0, stdout: str = "", stderr: str = ""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


def _fake_subprocess_run_factory(rev_count: str, gh_pr_calls: list):
    """Return a side_effect that mocks the subprocess sequence we drive.

    Recorded calls to `gh pr create` (full argv) land in ``gh_pr_calls``.
    """

    def side_effect(cmd, **kwargs):
        # gh pr list (existing-PR check) — return empty
        if cmd[:3] == ["gh", "pr", "list"]:
            return _completed(0, "", "")
        # git rev-list --count origin/<default>..HEAD
        if cmd[:3] == ["git", "rev-list", "--count"]:
            return _completed(0, rev_count, "")
        # gh pr create — record and refuse (GraphQL would fail anyway)
        if cmd[:3] == ["gh", "pr", "create"]:
            gh_pr_calls.append(list(cmd))
            return _completed(0, "https://example/pr/1", "")
        # git push, git fetch, git worktree, etc.
        return _completed(0, "", "")

    return side_effect


# ---------------------------------------------------------------------------
# Fixture (a): empty branch — hint printed, no `gh pr create`
# ---------------------------------------------------------------------------

def test_empty_branch_defers_pr_with_structured_hint(tmp_path, capsys):
    mgr = BranchManager(target_dir=tmp_path)
    gh_pr_calls: list = []

    with patch(
        "atdd.coach.commands.branch.subprocess.run",
        side_effect=_fake_subprocess_run_factory("0", gh_pr_calls),
    ), patch(
        "atdd.coach.commands.branch.resolve_default_branch",
        return_value="main",
    ):
        mgr._create_draft_pr(
            branch_name="feat/empty-test",
            issue_number=478,
            slug="empty-test",
            issue_type="cleanup",
            worktree_path=tmp_path,
        )

    out = capsys.readouterr().out

    assert gh_pr_calls == [], "must NOT invoke `gh pr create` on empty branch"
    assert "Draft PR deferred" in out
    assert "0 commits past" in out
    assert "atdd pr 478" in out
    assert "GraphQL" not in out  # no scary error wording
    assert "Warning: Could not create draft PR" not in out


# ---------------------------------------------------------------------------
# Fixture (b): non-empty branch — PR creation still attempted
# ---------------------------------------------------------------------------

def test_non_empty_branch_still_attempts_pr_creation(tmp_path):
    mgr = BranchManager(target_dir=tmp_path)
    gh_pr_calls: list = []

    with patch(
        "atdd.coach.commands.branch.subprocess.run",
        side_effect=_fake_subprocess_run_factory("3", gh_pr_calls),
    ), patch(
        "atdd.coach.commands.branch.resolve_default_branch",
        return_value="main",
    ), patch(
        "atdd.coach.commands.branch.ProjectConfig.from_config",
        side_effect=Exception("no config — fall back to slug"),
    ):
        mgr._create_draft_pr(
            branch_name="feat/non-empty-test",
            issue_number=478,
            slug="non-empty-test",
            issue_type="cleanup",
            worktree_path=tmp_path,
        )

    assert len(gh_pr_calls) == 1, "non-empty branch must invoke `gh pr create`"
    argv = gh_pr_calls[0]
    assert "--base" in argv and argv[argv.index("--base") + 1] == "main"
    assert "--head" in argv and argv[argv.index("--head") + 1] == "feat/non-empty-test"


# ---------------------------------------------------------------------------
# Fixture (c): `atdd pr <N>` on empty branch — clean exit + #467 hint
# ---------------------------------------------------------------------------

def test_atdd_pr_on_empty_branch_fails_clean_with_hint(tmp_path, capsys):
    mgr = PRManager(target_dir=tmp_path)
    gh_pr_calls: list = []

    def side_effect(cmd, **kwargs):
        # _detect_branch
        if cmd[:3] == ["git", "rev-parse", "--abbrev-ref"]:
            return _completed(0, "feat/empty\n", "")
        # _existing_pr_for_branch
        if cmd[:3] == ["gh", "pr", "list"]:
            return _completed(0, "", "")
        # _rev_count_past_default
        if cmd[:3] == ["git", "rev-list", "--count"]:
            return _completed(0, "0\n", "")
        if cmd[:3] == ["gh", "pr", "create"]:
            gh_pr_calls.append(list(cmd))
            return _completed(0, "", "")
        return _completed(0, "", "")

    with patch(
        "atdd.coach.commands.pr.subprocess.run",
        side_effect=side_effect,
    ), patch(
        "atdd.coach.commands.pr.resolve_default_branch",
        return_value="main",
    ):
        rc = mgr.pr(issue_number=478)

    out = capsys.readouterr().out
    assert rc == 1, "empty-branch path must exit non-zero"
    assert gh_pr_calls == [], "must NOT invoke `gh pr create` on empty branch"
    assert "0 commits past" in out
    assert "Fix:" in out
    # #467 contract: numbered prereqs, runnable as printed, no deprecated CLI
    assert "1." in out and "2." in out
    assert "atdd pr 478" in out
    assert "atdd update" not in out  # deprecated form must not appear
