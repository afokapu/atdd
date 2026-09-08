# URN: test:drive-state-machine:post-merge-advance-is-observable:C001-SMOKE-001-a-real-merged-pr-resolves-its-issue
# Acceptance: acc:drive-state-machine:C001-SMOKE-001-a-real-merged-pr-resolves-its-issue
# WMBT: wmbt:drive-state-machine:C001
# Phase: RED
# Layer: integration
"""C001-SMOKE-001 — a real merged PR resolves to the issue GitHub links.

The unit acceptances stub the fetch, so they prove the SPLIT but not that the
lookup asks GitHub the right thing. This drives the live projection: the defect
was that a PR whose closingIssuesReferences GitHub resolved perfectly well came
back as "no linked issue".
"""
from __future__ import annotations

import json
import subprocess

import pytest

from atdd.coach.commands.pr import PRManager
from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo
from atdd.coach.validators._observation import Observation

pytestmark = [pytest.mark.github_api, pytest.mark.platform]


def test_a_real_merged_pr_resolves_its_issue():
    if not is_atdd_source_repo():
        pytest.skip("toolkit-self acceptance; this repository's PRs are the subject")
    root = find_repo_root()

    out = subprocess.run(
        ["gh", "pr", "list", "--state", "merged", "--limit", "12",
         "--json", "number,closingIssuesReferences"],
        cwd=str(root), capture_output=True, text=True, timeout=90,
    ).stdout
    linked = next(
        (r for r in json.loads(out or "[]") if r.get("closingIssuesReferences")),
        None,
    )
    if linked is None:
        pytest.skip("no recently merged PR carries a closing reference")

    expected = linked["closingIssuesReferences"][0]["number"]
    reading = PRManager(target_dir=root).read_linked_issue(linked["number"])

    assert reading.observation is Observation.OBSERVED, (
        f"GitHub links PR #{linked['number']} to issue #{expected}; the resolver "
        f"reported {reading.observation} — {reading.reason}"
    )
    assert reading.payload["issue_number"] == expected
