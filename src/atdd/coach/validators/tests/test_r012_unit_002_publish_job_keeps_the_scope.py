# URN: test:govern-lifecycle:govern-lifecycle:R012-UNIT-002-the-publish-job-keeps-the-scope-the-token-needs
# Acceptance: acc:govern-lifecycle:R012-UNIT-002-the-publish-job-keeps-the-scope-the-token-needs
# WMBT: wmbt:govern-lifecycle:R012
# Phase: RED
# Layer: application
"""R012-UNIT-002 — the token and the scope are a pair; one without the other fails.

Supplying `GH_TOKEN` is worthless if the job's `permissions` do not carry write
access to contents, because that is what creating a release requires. The
repository default grants read only, so the scope must be declared on the job and
cannot be inferred.

This passes today — it is a regression guard, not a discovery. A future
least-privilege trim of the job's permissions would silently re-break publishing
in a way that looks nothing like the credential defect R012 fixes, and this states
the dependency so the trim fails loudly instead.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo


@pytest.mark.coder
@pytest.mark.platform
def test_the_release_job_declares_write_access_to_contents():
    if not is_atdd_source_repo():
        pytest.skip("reads this repository's own committed workflows")

    workflow = Path(find_repo_root()) / ".github" / "workflows" / "publish.yml"
    doc = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}

    job = (doc.get("jobs") or {}).get("tag-release")
    assert job, "publish.yml no longer defines a tag-release job — retire or retarget this check"

    permissions = job.get("permissions") or {}
    assert permissions.get("contents") == "write", (
        "creating a release writes to repository contents, and the repository "
        "default grants read only, so the job must declare it explicitly; got "
        f"{permissions!r}"
    )
