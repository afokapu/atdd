# URN: test:govern-lifecycle:gh-issue-create-block-l3:E033-INTEGRATION-002-precommit-allows-md-docs
# Acceptance: acc:govern-lifecycle:E033-INTEGRATION-002-precommit-allows-md-docs
# WMBT: wmbt:govern-lifecycle:E033
# Phase: RED
# Layer: backend.integration
"""AC-INTEGRATION-002: a staged markdown file with `gh issue create` in a code
fence passes the hook (exit 0) — *.md is exempt.

RED state: the pre-commit-gh-issue-create.sh hook template does not exist yet.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ._gh_issue_create_precommit_harness import init_repo, install_hook, run_precommit, stage

pytestmark = [pytest.mark.coach]


def test_precommit_allows_markdown_docs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    install_hook(repo)
    stage(
        repo,
        "docs/rule.md",
        "# The rule\n\nDo not run this:\n\n```sh\ngh issue create --title x\n```\n\nUse `atdd issue` instead.\n",
    )
    result = run_precommit(repo)
    assert result.returncode == 0, (
        f"markdown doc wrongly blocked (md should be exempt): {result.stdout}{result.stderr}"
    )
