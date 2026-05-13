# URN: test:govern-lifecycle:atdd-issue-canonical-path:E002-UNIT-002-gc-classifier
# Acceptance: acc:govern-lifecycle:E002-UNIT-002-gc-classifier
# Acceptance: acc:govern-lifecycle:E002-INTEGRATION-006-gc-lists-orphans
# Acceptance: acc:govern-lifecycle:E002-INTEGRATION-007-gc-apply-cleans
# Acceptance: acc:govern-lifecycle:E002-INTEGRATION-008-gc-spares-real-worktrees
# Acceptance: acc:govern-lifecycle:E002-INTEGRATION-009-gc-spares-non-launch-prompt-dirs
# WMBT: wmbt:govern-lifecycle:E002
# Phase: RED
# Layer: unit
"""
Tests for Phase 3 of E002: atdd worktree gc orphan detection and cleanup.

Covers:
  acc:govern-lifecycle:E002-UNIT-002-gc-classifier
  acc:govern-lifecycle:E002-INTEGRATION-006-gc-lists-orphans
  acc:govern-lifecycle:E002-INTEGRATION-007-gc-apply-cleans
  acc:govern-lifecycle:E002-INTEGRATION-008-gc-spares-real-worktrees
  acc:govern-lifecycle:E002-INTEGRATION-009-gc-spares-non-launch-prompt-dirs
"""
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LAUNCH_PROMPT = ".launch_prompt.txt"


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


def _make_orphan(parent: Path, name: str) -> Path:
    """Create a sibling dir that looks like an atdd orphan."""
    orphan = parent / name
    orphan.mkdir()
    (orphan / LAUNCH_PROMPT).write_text("session started\n")
    return orphan


def _make_wip_dir(parent: Path, name: str) -> Path:
    """Create a sibling dir with extra files (operator WIP — not an orphan)."""
    wip = parent / name
    wip.mkdir()
    (wip / LAUNCH_PROMPT).write_text("session started\n")
    (wip / "notes.md").write_text("work in progress\n")
    return wip


def _make_empty_dir(parent: Path, name: str) -> Path:
    d = parent / name
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# E002-UNIT-002: _is_orphan classifier
# ---------------------------------------------------------------------------

class TestIsOrphanUnit:
    """acc:govern-lifecycle:E002-UNIT-002-gc-classifier"""

    def test_launch_prompt_only_is_orphan(self, tmp_path):
        d = _make_orphan(tmp_path, "feat-test-slug")
        from atdd.coach.commands.worktree_gc import _is_orphan
        assert _is_orphan(d, set()) is True

    def test_extra_file_not_orphan(self, tmp_path):
        d = _make_wip_dir(tmp_path, "feat-wip-stuff")
        from atdd.coach.commands.worktree_gc import _is_orphan
        assert _is_orphan(d, set()) is False

    def test_real_worktree_not_orphan(self, tmp_path):
        d = _make_orphan(tmp_path, "feat-real-worktree")
        from atdd.coach.commands.worktree_gc import _is_orphan
        assert _is_orphan(d, {d.resolve()}) is False

    def test_empty_dir_not_orphan(self, tmp_path):
        d = _make_empty_dir(tmp_path, "feat-empty")
        from atdd.coach.commands.worktree_gc import _is_orphan
        assert _is_orphan(d, set()) is False

    def test_non_existent_path_not_orphan(self, tmp_path):
        from atdd.coach.commands.worktree_gc import _is_orphan
        assert _is_orphan(tmp_path / "does-not-exist", set()) is False


# ---------------------------------------------------------------------------
# E002-INTEGRATION-006: gc lists orphans (dry-run)
# ---------------------------------------------------------------------------

class TestGcListsOrphans:
    """acc:govern-lifecycle:E002-INTEGRATION-006-gc-lists-orphans"""

    def test_orphan_appears_in_result(self, tmp_path):
        project_parent = tmp_path
        main_repo = project_parent / "main"
        main_repo.mkdir()
        _init_git_repo(main_repo)

        orphan = _make_orphan(project_parent, "feat-some-slug")

        from atdd.coach.commands.worktree_gc import gc

        with patch("atdd.coach.commands.worktree_gc._real_worktree_paths",
                   return_value={main_repo.resolve()}):
            result = gc(repo_root=main_repo, apply=False)

        assert orphan.resolve() in [p.resolve() for p in result]

    def test_orphan_still_exists_after_dry_run(self, tmp_path):
        project_parent = tmp_path
        main_repo = project_parent / "main"
        main_repo.mkdir()
        _init_git_repo(main_repo)

        orphan = _make_orphan(project_parent, "feat-some-slug")

        from atdd.coach.commands.worktree_gc import gc
        with patch("atdd.coach.commands.worktree_gc._real_worktree_paths",
                   return_value={main_repo.resolve()}):
            gc(repo_root=main_repo, apply=False)

        assert orphan.exists()


# ---------------------------------------------------------------------------
# E002-INTEGRATION-007: gc --apply cleans orphans
# ---------------------------------------------------------------------------

class TestGcApplyCleans:
    """acc:govern-lifecycle:E002-INTEGRATION-007-gc-apply-cleans"""

    def test_apply_removes_orphan(self, tmp_path):
        project_parent = tmp_path
        main_repo = project_parent / "main"
        main_repo.mkdir()
        _init_git_repo(main_repo)

        orphan = _make_orphan(project_parent, "feat-gone")

        from atdd.coach.commands.worktree_gc import gc
        with patch("atdd.coach.commands.worktree_gc._real_worktree_paths",
                   return_value={main_repo.resolve()}):
            result = gc(repo_root=main_repo, apply=True)

        assert orphan.resolve() in [p.resolve() for p in result]
        assert not orphan.exists()

    def test_apply_returns_list_of_removed(self, tmp_path):
        project_parent = tmp_path
        main_repo = project_parent / "main"
        main_repo.mkdir()
        _init_git_repo(main_repo)

        orphan = _make_orphan(project_parent, "feat-gone")

        from atdd.coach.commands.worktree_gc import gc
        with patch("atdd.coach.commands.worktree_gc._real_worktree_paths",
                   return_value={main_repo.resolve()}):
            result = gc(repo_root=main_repo, apply=True)

        assert len(result) == 1


# ---------------------------------------------------------------------------
# E002-INTEGRATION-008: gc spares real worktrees
# ---------------------------------------------------------------------------

class TestGcSparesRealWorktrees:
    """acc:govern-lifecycle:E002-INTEGRATION-008-gc-spares-real-worktrees"""

    def test_real_worktree_with_launch_prompt_not_listed(self, tmp_path):
        project_parent = tmp_path
        main_repo = project_parent / "main"
        main_repo.mkdir()
        _init_git_repo(main_repo)

        real_wt = project_parent / "feat-real"
        real_wt.mkdir()
        (real_wt / LAUNCH_PROMPT).write_text("session\n")

        from atdd.coach.commands.worktree_gc import gc
        real_worktree_paths = {main_repo.resolve(), real_wt.resolve()}
        with patch("atdd.coach.commands.worktree_gc._real_worktree_paths",
                   return_value=real_worktree_paths):
            result = gc(repo_root=main_repo, apply=False)

        resolved_results = [p.resolve() for p in result]
        assert real_wt.resolve() not in resolved_results


# ---------------------------------------------------------------------------
# E002-INTEGRATION-009: gc spares dirs with non-.launch_prompt.txt files
# ---------------------------------------------------------------------------

class TestGcSparesNonLaunchPromptDirs:
    """acc:govern-lifecycle:E002-INTEGRATION-009-gc-spares-non-launch-prompt-dirs"""

    def test_dir_with_extra_file_not_listed(self, tmp_path):
        project_parent = tmp_path
        main_repo = project_parent / "main"
        main_repo.mkdir()
        _init_git_repo(main_repo)

        wip = _make_wip_dir(project_parent, "feat-operator-wip")

        from atdd.coach.commands.worktree_gc import gc
        with patch("atdd.coach.commands.worktree_gc._real_worktree_paths",
                   return_value={main_repo.resolve()}):
            result = gc(repo_root=main_repo, apply=False)

        resolved_results = [p.resolve() for p in result]
        assert wip.resolve() not in resolved_results

    def test_both_orphan_and_wip_present_only_orphan_listed(self, tmp_path):
        project_parent = tmp_path
        main_repo = project_parent / "main"
        main_repo.mkdir()
        _init_git_repo(main_repo)

        orphan = _make_orphan(project_parent, "feat-orphan")
        wip = _make_wip_dir(project_parent, "feat-wip")

        from atdd.coach.commands.worktree_gc import gc
        with patch("atdd.coach.commands.worktree_gc._real_worktree_paths",
                   return_value={main_repo.resolve()}):
            result = gc(repo_root=main_repo, apply=False)

        resolved_results = [p.resolve() for p in result]
        assert orphan.resolve() in resolved_results
        assert wip.resolve() not in resolved_results
