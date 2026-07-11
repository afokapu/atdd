# URN: test:govern-lifecycle:gh-issue-create-block-l3:E033-INTEGRATION-001-precommit-blocks-staged
# Acceptance: acc:govern-lifecycle:E033-INTEGRATION-001-precommit-blocks-staged
# WMBT: wmbt:govern-lifecycle:E033
# Phase: RED
# Layer: backend.integration
"""AC-INTEGRATION-001: staging a .sh with `gh issue create` makes the hook exit 1
with an educational error pointing at `atdd issue`.

RED state: the pre-commit-gh-issue-create.sh hook template does not exist yet.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ._gh_issue_create_precommit_harness import init_repo, install_hook, run_precommit, stage

pytestmark = [pytest.mark.coach]


def test_precommit_blocks_staged_script(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    install_hook(repo)
    stage(repo, "scripts/file_issue.sh", "#!/bin/sh\ngh issue create --title bug --body details\n")
    result = run_precommit(repo)
    assert result.returncode == 1, f"expected block (exit 1), got {result.returncode}"
    combined = result.stdout + result.stderr
    assert "atdd author issue" in combined, f"educational alternative missing: {combined!r}"
