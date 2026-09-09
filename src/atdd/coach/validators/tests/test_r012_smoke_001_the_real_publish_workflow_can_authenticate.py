# URN: test:govern-lifecycle:govern-lifecycle:R012-SMOKE-001-the-real-publish-workflow-can-authenticate
# Acceptance: acc:govern-lifecycle:R012-SMOKE-001-the-real-publish-workflow-can-authenticate
# WMBT: wmbt:govern-lifecycle:R012
# Phase: SMOKE
# Layer: application
"""R012-SMOKE-001 — the real committed workflow must be able to authenticate.

Reads this repository's own `publish.yml`, not a constructed one. A fixture here
would assert that the check works; it would not assert that this repository can
publish, which is the thing that has been false since v4.21.0.

Both halves are asserted together because either alone still fails: a token with
no `contents: write` is refused by the API, and the scope without a token never
reaches it.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo

_TOKEN_VARS = {"GH_TOKEN", "GITHUB_TOKEN"}
# The drain runs this entry point, which shells out to `gh release create`. The
# step's own command text never says "gh", so the requirement is invisible to any
# check that reads the step rather than knowing the callee.
_DRAIN_ENTRY_POINT = "drain_version_decided"


def _publish_job(repo_root: Path):
    workflow = repo_root / ".github" / "workflows" / "publish.yml"
    doc = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
    job = (doc.get("jobs") or {}).get("tag-release")
    assert job, "publish.yml no longer defines a tag-release job — retarget this check"
    return doc, job


@pytest.mark.coder
@pytest.mark.platform
def test_the_drain_step_has_the_credential_gh_reads():
    if not is_atdd_source_repo():
        pytest.skip("reads this repository's own committed workflow")

    doc, job = _publish_job(Path(find_repo_root()))
    available = set(doc.get("env") or {}) | set(job.get("env") or {})

    drain = [
        s for s in job.get("steps") or []
        if isinstance(s, dict) and _DRAIN_ENTRY_POINT in str(s.get("run") or "")
    ]
    assert drain, (
        f"no step runs {_DRAIN_ENTRY_POINT!r} — the publish path moved and this "
        "check is now measuring nothing"
    )

    for step in drain:
        names = available | set(step.get("env") or {})
        assert names & _TOKEN_VARS, (
            f"the step running {_DRAIN_ENTRY_POINT} has no GH_TOKEN or "
            "GITHUB_TOKEN in scope; the release worker shells out to "
            "`gh release create`, which refuses without one"
        )


@pytest.mark.coder
@pytest.mark.platform
def test_the_release_job_declares_write_access_to_contents():
    """The other half of the pair — a token without the scope fails just as surely."""
    if not is_atdd_source_repo():
        pytest.skip("reads this repository's own committed workflow")

    _doc, job = _publish_job(Path(find_repo_root()))
    permissions = job.get("permissions") or {}

    assert permissions.get("contents") == "write", (
        "creating a release writes to repository contents, and the repository "
        f"default grants read only, so the job must declare it: got {permissions!r}"
    )
