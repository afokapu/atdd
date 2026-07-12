# URN: test:govern-lifecycle:gh-issue-create-block-l3:E033-SMOKE-001-real-commit-rejects-staged-create
# Acceptance: acc:govern-lifecycle:E033-SMOKE-001-real-commit-rejects-staged-create
# WMBT: wmbt:govern-lifecycle:E033
# Phase: RED
# Layer: backend.integration
"""AC-SMOKE-001: a real `git commit` is rejected when a staged .sh contains
`gh issue create` — driving the real git pre-commit invocation path, not a
direct hook call.

RED state: the pre-commit-gh-issue-create.sh hook template does not exist yet.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ._gh_issue_create_precommit_harness import init_repo, install_hook, stage

pytestmark = [pytest.mark.coach]


def test_real_git_commit_is_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    install_hook(repo)
    stage(repo, "automation.sh", "#!/bin/sh\ngh issue create --title smoke\n")

    result = subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "add automation"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0, "real git commit was NOT rejected by the pre-commit hook"
    combined = result.stdout + result.stderr
    assert "atdd author issue" in combined, f"educational alternative missing: {combined!r}"

    # No commit object should exist on the branch.
    log = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--count", "--all"],
        capture_output=True,
        text=True,
    )
    assert log.stdout.strip() == "0", f"a commit was created despite the hook block: {log.stdout!r}"
