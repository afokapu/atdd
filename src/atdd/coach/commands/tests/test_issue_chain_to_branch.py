# URN: test:govern-lifecycle:atdd-issue-canonical-path:E002-INTEGRATION-003-chain-creates-worktree
# Acceptance: acc:govern-lifecycle:E002-INTEGRATION-003-chain-creates-worktree
# Acceptance: acc:govern-lifecycle:E002-INTEGRATION-004-no-branch-skips-worktree
# Acceptance: acc:govern-lifecycle:E002-INTEGRATION-005-output-distinguishes-created-vs-intent
# WMBT: wmbt:govern-lifecycle:E002
# Phase: RED
# Layer: integration
"""
Tests for Phase 2 of E002: chaining atdd issue <slug> to worktree creation.

Covers:
  acc:govern-lifecycle:E002-INTEGRATION-003-chain-creates-worktree
  acc:govern-lifecycle:E002-INTEGRATION-004-no-branch-skips-worktree
  acc:govern-lifecycle:E002-INTEGRATION-005-output-distinguishes-created-vs-intent
"""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_git_repo(path: Path, branch: str = "main") -> None:
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


def _setup_lifecycle(tmp_path: Path):
    """Create a minimal ATDD-initialised repo on main and return lifecycle."""
    _init_git_repo(tmp_path, branch="main")
    from atdd.coach.commands.issue_lifecycle import IssueLifecycle
    return IssueLifecycle(target_dir=tmp_path)


def _make_manifest_with_issue(tmp_path: Path, slug: str, issue_number: int) -> None:
    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "sessions": [
            {
                "id": str(issue_number),
                "slug": slug,
                "issue_number": issue_number,
                "status": "INIT",
                "type": "implementation",
                "created": "2026-05-13",
                "archived": None,
                "file": None,
            }
        ]
    }
    with open(atdd_dir / "manifest.yaml", "w") as f:
        yaml.dump(manifest, f)


# ---------------------------------------------------------------------------
# E002-INTEGRATION-003: chain creates worktree
# ---------------------------------------------------------------------------

class TestChainCreatesWorktree:
    """acc:govern-lifecycle:E002-INTEGRATION-003-chain-creates-worktree"""

    def test_create_branch_called_when_no_branch_false(self, tmp_path):
        lifecycle = _setup_lifecycle(tmp_path)
        _make_manifest_with_issue(tmp_path, "test-slug", 99)

        create_branch_calls = []

        def fake_create_branch(issue_number, slug, prefix):
            create_branch_calls.append((issue_number, slug, prefix))
            return tmp_path.parent / f"{prefix}-{slug}"

        with patch.object(lifecycle, "_create_branch", side_effect=fake_create_branch), \
             patch("atdd.coach.commands.issue.IssueManager") as mock_mgr_cls, \
             patch.object(lifecycle, "enter", return_value=0):

            mock_mgr = mock_mgr_cls.return_value
            mock_mgr.new.return_value = 0
            mock_mgr._slugify.return_value = "test-slug"

            lifecycle.create(slug="test-slug", no_branch=False)

        assert len(create_branch_calls) == 1
        assert create_branch_calls[0][0] == 99

    def test_worktree_path_in_output_when_created(self, tmp_path, capsys):
        lifecycle = _setup_lifecycle(tmp_path)
        _make_manifest_with_issue(tmp_path, "test-slug", 99)

        fake_path = tmp_path.parent / "feat-test-slug"

        with patch.object(lifecycle, "_create_branch", return_value=fake_path), \
             patch("atdd.coach.commands.issue.IssueManager") as mock_mgr_cls, \
             patch.object(lifecycle, "enter", return_value=0):

            mock_mgr = mock_mgr_cls.return_value
            mock_mgr.new.return_value = 0
            mock_mgr._slugify.return_value = "test-slug"

            lifecycle.create(slug="test-slug", no_branch=False)

        out = capsys.readouterr().out
        assert "created at" in out or str(fake_path) in out


# ---------------------------------------------------------------------------
# E002-INTEGRATION-004: --no-branch skips worktree
# ---------------------------------------------------------------------------

class TestNoBranchSkipsWorktree:
    """acc:govern-lifecycle:E002-INTEGRATION-004-no-branch-skips-worktree"""

    def test_create_branch_not_called_when_no_branch_true(self, tmp_path):
        lifecycle = _setup_lifecycle(tmp_path)
        _make_manifest_with_issue(tmp_path, "test-slug", 99)

        create_branch_calls = []

        def fake_create_branch(*args, **kwargs):
            create_branch_calls.append(args)
            return None

        with patch.object(lifecycle, "_create_branch", side_effect=fake_create_branch), \
             patch("atdd.coach.commands.issue.IssueManager") as mock_mgr_cls, \
             patch.object(lifecycle, "enter", return_value=0):

            mock_mgr = mock_mgr_cls.return_value
            mock_mgr.new.return_value = 0
            mock_mgr._slugify.return_value = "test-slug"

            lifecycle.create(slug="test-slug", no_branch=True)

        assert len(create_branch_calls) == 0

    def test_not_created_message_when_no_branch_true(self, tmp_path, capsys):
        lifecycle = _setup_lifecycle(tmp_path)
        _make_manifest_with_issue(tmp_path, "test-slug", 99)

        with patch.object(lifecycle, "_create_branch") as mock_cb, \
             patch("atdd.coach.commands.issue.IssueManager") as mock_mgr_cls, \
             patch.object(lifecycle, "enter", return_value=0):

            mock_mgr = mock_mgr_cls.return_value
            mock_mgr.new.return_value = 0
            mock_mgr._slugify.return_value = "test-slug"

            lifecycle.create(slug="test-slug", no_branch=True)

        mock_cb.assert_not_called()
        out = capsys.readouterr().out
        assert "not created" in out


# ---------------------------------------------------------------------------
# E002-INTEGRATION-005: output distinguishes created vs intent
# ---------------------------------------------------------------------------

class TestOutputDistinguishesCreatedVsIntent:
    """acc:govern-lifecycle:E002-INTEGRATION-005-output-distinguishes-created-vs-intent"""

    def test_created_output_contains_tick_created(self, tmp_path, capsys):
        lifecycle = _setup_lifecycle(tmp_path)
        _make_manifest_with_issue(tmp_path, "test-slug", 99)
        fake_path = tmp_path.parent / "feat-test-slug"

        with patch.object(lifecycle, "_create_branch", return_value=fake_path), \
             patch("atdd.coach.commands.issue.IssueManager") as mock_mgr_cls, \
             patch.object(lifecycle, "enter", return_value=0):

            mock_mgr = mock_mgr_cls.return_value
            mock_mgr.new.return_value = 0
            mock_mgr._slugify.return_value = "test-slug"

            lifecycle.create(slug="test-slug", no_branch=False)

        out = capsys.readouterr().out
        assert "✓ created at" in out

    def test_intent_output_contains_not_created(self, tmp_path, capsys):
        lifecycle = _setup_lifecycle(tmp_path)
        _make_manifest_with_issue(tmp_path, "test-slug", 99)

        with patch.object(lifecycle, "_create_branch") as mock_cb, \
             patch("atdd.coach.commands.issue.IssueManager") as mock_mgr_cls, \
             patch.object(lifecycle, "enter", return_value=0):

            mock_mgr = mock_mgr_cls.return_value
            mock_mgr.new.return_value = 0
            mock_mgr._slugify.return_value = "test-slug"

            lifecycle.create(slug="test-slug", no_branch=True)

        mock_cb.assert_not_called()
        out = capsys.readouterr().out
        assert "(not created" in out
