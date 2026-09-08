# URN: test:coach-ops:merge-outcome-classification:C001-SMOKE-001-the-real-verdict-comes-from-the-pull-request
# Acceptance: acc:coach-ops:C001-SMOKE-001-the-real-verdict-comes-from-the-pull-request
# WMBT: wmbt:coach-ops:C001
# Phase: RED
# Layer: integration
"""C001-SMOKE-001 — the probe agrees with GitHub about real pull requests.

The unit acceptances stub `_run_gh`, so they prove the parsing and the
fail-closed policy but never that the query itself asks GitHub the right thing.
This runs the real probe against a pull request this repository actually merged,
and against one that is open, so the two must come back different.

Skips rather than passes when the repository offers no such pair.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from atdd.coach.commands import merge_cascade as mc
from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo

pytestmark = [pytest.mark.github_api, pytest.mark.platform]


def _one(state: str):
    out = subprocess.run(
        ["gh", "pr", "list", "--state", state, "--limit", "1", "--json", "number"],
        cwd=str(find_repo_root()), capture_output=True, text=True, timeout=60,
    ).stdout
    rows = json.loads(out or "[]")
    return rows[0]["number"] if rows else None


def test_the_real_verdict_comes_from_the_pull_request():
    if not is_atdd_source_repo():
        pytest.skip("toolkit-self acceptance; this repository's PRs are the subject")

    merged, open_pr = _one("merged"), _one("open")
    if merged is None or open_pr is None:
        pytest.skip("need one merged and one open PR to tell the two apart")

    assert mc._pr_is_merged(merged) is True, (
        f"PR #{merged} is merged on GitHub; the probe that decides whether a "
        "failed `gh pr merge` halts the cascade must see that"
    )
    assert mc._pr_is_merged(open_pr) is False, (
        f"PR #{open_pr} is open; reporting it merged would wave a genuine "
        "merge failure through"
    )
