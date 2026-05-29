# URN: test:govern-lifecycle:gh-issue-create-block-l3:E033-UNIT-001-precommit-regex-precise
# Acceptance: acc:govern-lifecycle:E033-UNIT-001-precommit-regex-precise
# WMBT: wmbt:govern-lifecycle:E033
# Phase: RED
# Layer: backend.unit
"""AC-UNIT-001: the pre-commit matcher flags added `gh issue create` lines precisely.

Matches added lines `+gh issue create x` and `+    gh issue create x` (indented),
but NOT `+gh issuecreated` (word boundary) nor removed lines (`^\\+` anchor).

RED state: the pre-commit-gh-issue-create.sh hook template does not exist yet.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ._gh_issue_create_precommit_harness import init_repo, install_hook, run_precommit, stage

pytestmark = [pytest.mark.coach]


def test_added_exact_line_is_flagged(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    install_hook(repo)
    stage(repo, "automation.sh", "#!/bin/sh\ngh issue create --title x\n")
    result = run_precommit(repo)
    assert result.returncode == 1, f"exact added line not flagged: exit {result.returncode}"


def test_added_indented_line_is_flagged(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    install_hook(repo)
    stage(repo, "automation.sh", "#!/bin/sh\nif true; then\n    gh issue create --title x\nfi\n")
    result = run_precommit(repo)
    assert result.returncode == 1, f"indented added line not flagged: exit {result.returncode}"


def test_near_miss_word_is_not_flagged(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    install_hook(repo)
    stage(repo, "automation.sh", "#!/bin/sh\ngh issuecreated --title x\n")
    result = run_precommit(repo)
    assert result.returncode == 0, f"`gh issuecreated` wrongly flagged: {result.stdout}{result.stderr}"


def test_removed_line_is_not_flagged(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    # Commit a baseline containing the pattern BEFORE the hook is installed,
    # so the baseline commit is not itself blocked.
    stage(repo, "automation.sh", "#!/bin/sh\ngh issue create --title x\necho keep\n")
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "baseline"], check=True, capture_output=True)
    install_hook(repo)
    # Now stage a removal of the offending line — staged diff shows `-gh issue create`.
    stage(repo, "automation.sh", "#!/bin/sh\necho keep\n")
    result = run_precommit(repo)
    assert result.returncode == 0, f"removed line wrongly flagged (^+ anchor): {result.stdout}{result.stderr}"
