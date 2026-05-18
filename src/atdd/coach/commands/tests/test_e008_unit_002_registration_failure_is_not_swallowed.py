# URN: test:govern-lifecycle:reliable-manifest-registration:E008-UNIT-002-registration-failure-is-not-swallowed
# Acceptance: acc:govern-lifecycle:E008-UNIT-002-registration-failure-is-not-swallowed
# WMBT: wmbt:govern-lifecycle:E008
# Phase: RED
# Layer: unit
"""E008-UNIT-002 — _commit_manifest_change propagates a genuine manifest-commit
failure to its caller for the issue-registration verb, while the status-mirror
verb keeps the tolerant warning-and-return behavior.

Issue #738: today _commit_manifest_change swallows every ManifestCommitError as
a printed warning and returns, so `atdd issue <slug>` reports success with an
unregistered issue. The registration path must surface the failure (so the verb
can exit non-zero); the status-mirror path (`atdd update --status`) must stay
tolerant because transitions for issues created outside the CLI are valid.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.issue import IssueManager
from atdd.coach.utils.git import ManifestCommitError

pytestmark = [pytest.mark.platform]


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args), cwd=str(cwd), capture_output=True, text=True, check=True
    )


def _repo_with_untracked_manifest(tmp_path: Path, branch: str = "feat/demo") -> Path:
    """A git repo whose .atdd/manifest.yaml exists on disk but is NOT tracked —
    a genuine ManifestCommitError condition (refusing to commit untracked path)."""
    _run("git", "init", "-q", "-b", "main", cwd=tmp_path)
    _run("git", "config", "user.email", "test@example.com", cwd=tmp_path)
    _run("git", "config", "user.name", "Test User", cwd=tmp_path)
    _run("git", "config", "commit.gpgsign", "false", cwd=tmp_path)

    (tmp_path / "README.md").write_text("init\n", encoding="utf-8")
    _run("git", "add", "README.md", cwd=tmp_path)
    _run("git", "commit", "-q", "-m", "initial", cwd=tmp_path)
    _run("git", "checkout", "-q", "-b", branch, cwd=tmp_path)

    (tmp_path / ".atdd").mkdir()
    # Written but deliberately NOT `git add`-ed → untracked.
    (tmp_path / ".atdd" / "manifest.yaml").write_text(
        "sessions: []\n", encoding="utf-8"
    )
    return tmp_path


def test_registration_verb_surfaces_genuine_failure(tmp_path: Path) -> None:
    """Scenario A: the issue-registration verb must NOT silently return after a
    warning — it surfaces the failure (raises ManifestCommitError)."""
    repo = _repo_with_untracked_manifest(tmp_path)
    manager = IssueManager(target_dir=repo)

    with pytest.raises(ManifestCommitError):
        manager._commit_manifest_change(
            verb="atdd issue",
            message="chore(coach): register issue #99 in manifest",
        )


def test_status_mirror_verb_stays_tolerant(tmp_path: Path, capsys) -> None:
    """Scenario B: the status-mirror verb keeps the tolerant behavior — it prints
    a warning and returns normally without raising."""
    repo = _repo_with_untracked_manifest(tmp_path)
    manager = IssueManager(target_dir=repo)

    # Must not raise.
    manager._commit_manifest_change(
        verb="atdd update --status",
        message="chore(coach): mirror issue #99 status → SMOKE in manifest",
    )

    out = capsys.readouterr().out
    assert "manifest" in out.lower()
