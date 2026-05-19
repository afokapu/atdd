# Acceptance: acc:govern-lifecycle:E012-UNIT-004-branch-self-heals-missing-manifest-entry
# Acceptance: acc:govern-lifecycle:Y005-UNIT-001-issue-reconcile-backfills-unregistered
"""Unit tests for self-healing manifest backfill in atdd branch and atdd issue reconcile (#775).

Problem: when issue #N exists on GitHub but is absent from .atdd/manifest.yaml,
`atdd branch <N>` printed "not found in manifest" and exited 1 — blocking
worktree creation.

Fix:
  - BranchManager._backfill_from_github() synthesises the sessions entry from
    gh issue view output and appends it to the manifest.
  - BranchManager.branch() calls _backfill_from_github() before erroring.
  - IssueManager.reconcile() fetches all open atdd-issues and backfills any
    missing from the manifest in one pass.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manifest(sessions: list[dict]) -> dict:
    return {"sessions": sessions}


def _write_manifest(path: Path, sessions: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump({"sessions": sessions}, default_flow_style=False))


def _make_gh_issue_json(number: int, slug: str, status: str = "INIT") -> dict:
    """Minimal gh issue JSON as returned by `gh issue view --json ...`."""
    return {
        "number": number,
        "title": f"feat(atdd): {slug.replace('-', ' ').title()} (#{number})",
        "state": "OPEN",
        "createdAt": "2026-05-19T00:00:00Z",
        "labels": [{"name": f"atdd:{status}"}, {"name": "atdd-issue"}],
        "body": f"## Issue Metadata\n- wagon: govern-lifecycle\n- type: implementation",
    }


# ---------------------------------------------------------------------------
# E012-UNIT-004 — BranchManager self-heals missing manifest entry
# ---------------------------------------------------------------------------

class TestBranchManagerSelfHeal:
    """BranchManager.branch() must call _backfill_from_github() before erroring."""

    def test_backfill_method_exists(self) -> None:
        """E012-UNIT-004: BranchManager must expose _backfill_from_github(issue_number)."""
        from atdd.coach.commands.branch import BranchManager
        manager = BranchManager(Path("/tmp/fake"))
        assert hasattr(manager, "_backfill_from_github"), (
            "BranchManager must have _backfill_from_github(issue_number) method"
        )

    def test_backfill_synthesises_entry_from_gh(self, tmp_path: Path) -> None:
        """E012-UNIT-004: _backfill_from_github() appends a sessions entry synthesised from gh output."""
        manifest_path = tmp_path / ".atdd" / "manifest.yaml"
        _write_manifest(manifest_path, sessions=[])

        gh_json = _make_gh_issue_json(number=775, slug="on-main-guard-rejects-manifest-registration-commit")

        from atdd.coach.commands.branch import BranchManager
        manager = BranchManager(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(gh_json)
            mock_run.return_value = mock_result

            entry = manager._backfill_from_github(775)

        assert entry is not None, "_backfill_from_github must return the new entry"
        assert entry["issue_number"] == 775
        assert entry["slug"] == "on-main-guard-rejects-manifest-registration-commit"

        # Manifest must now contain the entry
        updated = yaml.safe_load(manifest_path.read_text()) or {}
        slugs = [s.get("slug") for s in updated.get("sessions", [])]
        assert "on-main-guard-rejects-manifest-registration-commit" in slugs, (
            "manifest must contain the backfilled entry after _backfill_from_github"
        )

    def test_backfill_returns_none_when_gh_fails(self, tmp_path: Path) -> None:
        """E012-UNIT-004: _backfill_from_github() returns None when gh CLI fails."""
        manifest_path = tmp_path / ".atdd" / "manifest.yaml"
        _write_manifest(manifest_path, sessions=[])

        from atdd.coach.commands.branch import BranchManager
        manager = BranchManager(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_result.stderr = "error: not found"
            mock_run.return_value = mock_result

            entry = manager._backfill_from_github(9999)

        assert entry is None, "_backfill_from_github must return None when gh CLI fails"

    def test_branch_no_longer_errors_when_entry_missing_but_gh_succeeds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """E012-UNIT-004: branch() must NOT return 1 with 'not found' when gh can supply the issue."""
        manifest_path = tmp_path / ".atdd" / "manifest.yaml"
        _write_manifest(manifest_path, sessions=[])

        gh_json = _make_gh_issue_json(775, "on-main-guard-rejects-manifest-registration-commit")

        # Patch subprocess.run for the gh call inside _backfill_from_github
        # and mock out the rest of branch() so it doesn't try to create a real worktree.
        from atdd.coach.commands.branch import BranchManager

        calls: list[list[str]] = []

        def _fake_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            calls.append(list(cmd))
            mock = MagicMock()
            # gh issue view → success
            if "gh" in cmd and "issue" in cmd and "view" in cmd:
                mock.returncode = 0
                mock.stdout = json.dumps(gh_json)
            # detect_worktree_layout git calls → success
            elif "git" in cmd and "worktree" in cmd and "list" in cmd:
                mock.returncode = 0
                mock.stdout = f"{str(tmp_path)}\n{str(tmp_path.parent / 'main')}\n"
            elif "git" in cmd:
                mock.returncode = 0
                mock.stdout = ""
            else:
                mock.returncode = 0
                mock.stdout = ""
            mock.stderr = ""
            return mock

        monkeypatch.setattr(subprocess, "run", _fake_run)
        monkeypatch.setattr(
            "atdd.coach.utils.repo.detect_worktree_layout",
            lambda path: "worktree-ready",
        )

        manager = BranchManager(tmp_path)
        # We do NOT expect "not found in manifest" to be printed and rc=1
        # The call may still fail (no real git), but it must NOT fail at manifest lookup.
        import io
        import sys
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            rc = manager.branch(775)
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()
        assert "not found in manifest" not in output, (
            f"branch() must not print 'not found in manifest' when gh can supply the issue; "
            f"got: {output!r}"
        )


# ---------------------------------------------------------------------------
# Y005-UNIT-001 — IssueManager.reconcile() backfills unregistered issues
# ---------------------------------------------------------------------------

class TestIssueManagerReconcile:
    """IssueManager must expose reconcile() and use it to backfill missing entries."""

    def test_reconcile_method_exists(self) -> None:
        """Y005-UNIT-001: IssueManager must expose reconcile()."""
        from atdd.coach.commands.issue import IssueManager
        manager = IssueManager(Path("/tmp/fake"))
        assert hasattr(manager, "reconcile"), (
            "IssueManager must have a reconcile() method"
        )

    def test_reconcile_adds_missing_issues(self, tmp_path: Path) -> None:
        """Y005-UNIT-001: reconcile() backfills issues found on GitHub but absent from manifest."""
        manifest_path = tmp_path / ".atdd" / "manifest.yaml"
        # Manifest has issue 100 but NOT 101
        _write_manifest(manifest_path, sessions=[
            {"id": "100", "slug": "existing-issue", "issue_number": 100,
             "type": "implementation", "status": "INIT", "created": "2026-01-01"},
        ])

        config_path = tmp_path / ".atdd" / "config.yaml"
        config_path.write_text("github:\n  repo: owner/repo\n  project_id: PVT_1\n")

        # Simulate two open atdd-issues on GitHub: #100 (already in manifest) and #101 (missing)
        open_issues = [
            {"number": 100, "title": "existing issue", "createdAt": "2026-01-01T00:00:00Z",
             "labels": [{"name": "atdd-issue"}, {"name": "atdd:INIT"}]},
            {"number": 101, "title": "feat(atdd): new issue (#101)", "createdAt": "2026-05-19T00:00:00Z",
             "labels": [{"name": "atdd-issue"}, {"name": "atdd:PLANNED"}]},
        ]

        from atdd.coach.commands.issue import IssueManager

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(open_issues)
            mock_run.return_value = mock_result

            manager = IssueManager(tmp_path)
            rc = manager.reconcile()

        assert rc == 0, f"reconcile() must return 0 on success; got {rc}"

        updated = yaml.safe_load(manifest_path.read_text()) or {}
        numbers = [s.get("issue_number") for s in updated.get("sessions", [])]
        assert 101 in numbers, (
            f"reconcile() must add issue #101 to the manifest; sessions={updated['sessions']}"
        )
        assert 100 in numbers, (
            f"reconcile() must keep existing issue #100; sessions={updated['sessions']}"
        )

    def test_reconcile_is_idempotent(self, tmp_path: Path) -> None:
        """Y005-UNIT-001: reconcile() running twice must not duplicate entries."""
        manifest_path = tmp_path / ".atdd" / "manifest.yaml"
        _write_manifest(manifest_path, sessions=[
            {"id": "100", "slug": "existing-issue", "issue_number": 100,
             "type": "implementation", "status": "INIT", "created": "2026-01-01"},
        ])

        config_path = tmp_path / ".atdd" / "config.yaml"
        config_path.write_text("github:\n  repo: owner/repo\n  project_id: PVT_1\n")

        open_issues = [
            {"number": 100, "title": "existing issue", "createdAt": "2026-01-01T00:00:00Z",
             "labels": [{"name": "atdd-issue"}, {"name": "atdd:INIT"}]},
        ]

        from atdd.coach.commands.issue import IssueManager

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(open_issues)
            mock_run.return_value = mock_result

            manager = IssueManager(tmp_path)
            manager.reconcile()
            manager.reconcile()

        updated = yaml.safe_load(manifest_path.read_text()) or {}
        numbers = [s.get("issue_number") for s in updated.get("sessions", [])]
        assert numbers.count(100) == 1, (
            f"reconcile() must not duplicate entries; numbers={numbers}"
        )
