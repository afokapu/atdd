# URN: test:govern-lifecycle:pr-base-guard-stack-awareness:C018-SMOKE-001-the-live-open-pr-set-passes-the-guard
# Acceptance: acc:govern-lifecycle:C018-SMOKE-001-the-live-open-pr-set-passes-the-guard
# WMBT: wmbt:govern-lifecycle:C018
# Phase: RED
# Layer: integration
"""C018-SMOKE-001 — the repository's live open PRs pass the guard.

Synthetic fixtures cannot show the failure this issue is about: the queue-wide
red-lighting only appears against a REAL stack in the REAL listing. This runs the
end-to-end scanner over `gh pr list` and asserts that no violation is attributed
to a PR whose base is another open PR's head.

It stays honest when the repository happens to hold no stack: that is reported as
a skip, not a silent pass, so the acceptance never claims to have observed
something it could not see.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo
from atdd.coach.validators.test_pr_base_branch import (
    _fetch_open_prs,
    evaluate_base_violations,
)
from atdd.coach.utils.default_branch import resolve_default_branch

pytestmark = [pytest.mark.github_api, pytest.mark.platform]


def test_the_live_open_pr_set_passes_the_guard():
    if not is_atdd_source_repo():
        pytest.skip("toolkit-self acceptance; this repository's queue is the subject")

    root = find_repo_root()
    open_prs = _fetch_open_prs(root)
    if not open_prs:
        pytest.skip("no open pull requests to evaluate")

    heads = {pr.get("headRefName") for pr in open_prs if pr.get("headRefName")}
    stacked = [pr for pr in open_prs if pr.get("baseRefName") in heads]
    if not stacked:
        pytest.skip("no stacked PR in the live queue; nothing for this to observe")

    violations = evaluate_base_violations(open_prs, resolve_default_branch(root))
    offending = {v.location for v in violations}
    stacked_locations = {f"PR#{pr['number']}" for pr in stacked}

    assert not (offending & stacked_locations), (
        "the guard flagged tracked stack(s) whose base is another open PR's head, "
        f"which fails validate-coach on every PR in the queue: "
        f"{sorted(offending & stacked_locations)}"
    )
