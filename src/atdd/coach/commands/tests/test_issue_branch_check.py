"""
Tests for Phase 1 of E002: branch-check guard on atdd issue <slug>.

Covers:
  acc:govern-lifecycle:E002-UNIT-001-branch-check-helper
  acc:govern-lifecycle:E002-INTEGRATION-001-branch-check-rejects-non-main
  acc:govern-lifecycle:E002-INTEGRATION-002-force-overrides-branch-check
"""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_git_repo(path: Path, branch: str = "main") -> None:
    """Create a bare git repo at path with one commit on `branch`."""
    subprocess.run(["git", "init", "-b", branch, str(path)], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t.com"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"],
                   check=True, capture_output=True)
    (path / "README.md").write_text("init\n")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "init"],
                   check=True, capture_output=True)


def _checkout_branch(path: Path, branch: str) -> None:
    subprocess.run(
        ["git", "-C", str(path), "checkout", "-b", branch],
        check=True, capture_output=True,
    )


# ---------------------------------------------------------------------------
# E002-UNIT-001: _check_on_main_branch helper
# ---------------------------------------------------------------------------

class TestCheckOnMainBranchUnit:
    """acc:govern-lifecycle:E002-UNIT-001-branch-check-helper"""

    def test_returns_true_on_main(self, tmp_path):
        _init_git_repo(tmp_path, branch="main")
        from atdd.coach.commands.issue_lifecycle import _check_on_main_branch
        ok, msg = _check_on_main_branch(tmp_path)
        assert ok is True
        assert msg is None

    def test_returns_false_on_feature_branch(self, tmp_path):
        _init_git_repo(tmp_path, branch="main")
        _checkout_branch(tmp_path, "feat/something")
        from atdd.coach.commands.issue_lifecycle import _check_on_main_branch
        ok, msg = _check_on_main_branch(tmp_path)
        assert ok is False
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_error_message_names_current_branch(self, tmp_path):
        _init_git_repo(tmp_path, branch="main")
        _checkout_branch(tmp_path, "docs/my-notes")
        from atdd.coach.commands.issue_lifecycle import _check_on_main_branch
        ok, msg = _check_on_main_branch(tmp_path)
        assert ok is False
        assert "docs/my-notes" in msg

    def test_fail_open_when_git_unavailable(self, tmp_path):
        from atdd.coach.commands.issue_lifecycle import _check_on_main_branch
        with patch("subprocess.run", side_effect=FileNotFoundError):
            ok, msg = _check_on_main_branch(tmp_path)
        assert ok is True
        assert msg is None

    def test_fail_open_on_git_error(self, tmp_path):
        from atdd.coach.commands.issue_lifecycle import _check_on_main_branch
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            ok, msg = _check_on_main_branch(tmp_path)
        assert ok is True


# ---------------------------------------------------------------------------
# E002-INTEGRATION-001: non-main branch rejects
# ---------------------------------------------------------------------------

class TestBranchCheckRejectsNonMain:
    """acc:govern-lifecycle:E002-INTEGRATION-001-branch-check-rejects-non-main"""

    def test_create_exits_one_on_non_main_branch(self, tmp_path):
        _init_git_repo(tmp_path, branch="main")
        _checkout_branch(tmp_path, "feat/something")

        from atdd.coach.commands.issue_lifecycle import IssueLifecycle
        lifecycle = IssueLifecycle(target_dir=tmp_path)

        # Patch IssueManager.new so we never touch GitHub
        with patch("atdd.coach.commands.issue.IssueManager") as mock_mgr_cls:
            mock_mgr_cls.return_value.new.return_value = 0
            rc = lifecycle.create(slug="test-slug", force=False)

        assert rc == 1

    def test_error_output_contains_educational_message(self, tmp_path, capsys):
        _init_git_repo(tmp_path, branch="main")
        _checkout_branch(tmp_path, "feat/something")

        from atdd.coach.commands.issue_lifecycle import IssueLifecycle
        lifecycle = IssueLifecycle(target_dir=tmp_path)

        with patch("atdd.coach.commands.issue.IssueManager"):
            lifecycle.create(slug="test-slug", force=False)

        out = capsys.readouterr().out
        assert "main" in out.lower() or "branch" in out.lower()


# ---------------------------------------------------------------------------
# E002-INTEGRATION-002: --force overrides branch check
# ---------------------------------------------------------------------------

class TestForceOverridesBranchCheck:
    """acc:govern-lifecycle:E002-INTEGRATION-002-force-overrides-branch-check"""

    def test_force_does_not_return_one_due_to_check(self, tmp_path, capsys):
        _init_git_repo(tmp_path, branch="main")
        _checkout_branch(tmp_path, "feat/something")

        # Patch everything past the branch check so we can observe the check result
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle
        lifecycle = IssueLifecycle(target_dir=tmp_path)

        with patch("atdd.coach.commands.issue.IssueManager") as mock_mgr_cls:
            mock_mgr = mock_mgr_cls.return_value
            mock_mgr.new.return_value = 1  # downstream fails — that's OK, not from check
            mock_mgr._slugify.return_value = "test-slug"
            rc = lifecycle.create(slug="test-slug", force=True)

        out = capsys.readouterr().out
        # The branch check alone should not have returned 1 — the downstream failure is ok
        # What we verify: "Warning" about branch appeared (not "Error:")
        assert "Warning" in out or rc != 1 or "force" in out.lower()

    def test_warning_printed_not_error_on_force(self, tmp_path, capsys):
        _init_git_repo(tmp_path, branch="main")
        _checkout_branch(tmp_path, "feat/something")

        from atdd.coach.commands.issue_lifecycle import IssueLifecycle
        lifecycle = IssueLifecycle(target_dir=tmp_path)

        with patch("atdd.coach.commands.issue.IssueManager") as mock_mgr_cls:
            mock_mgr_cls.return_value.new.return_value = 1
            mock_mgr_cls.return_value._slugify.return_value = "test-slug"
            lifecycle.create(slug="test-slug", force=True)

        out = capsys.readouterr().out
        assert "Warning" in out
        assert "Error:" not in out.split("Warning")[0]
