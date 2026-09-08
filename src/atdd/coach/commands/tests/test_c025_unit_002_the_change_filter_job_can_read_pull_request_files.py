# URN: test:govern-lifecycle:govern-lifecycle:C025-UNIT-002
# Acceptance: acc:govern-lifecycle:C025-UNIT-002-the-change-filter-job-can-read-pull-request-files
# WMBT: wmbt:govern-lifecycle:C025
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""C025-UNIT-002 — the grant must reach the job that actually makes the API call.

C025-UNIT-001 pins that a `permissions:` block exists. That is necessary and not
sufficient: GitHub resolves permissions per job, so a workflow-level grant is
inherited only by jobs that declare none of their own. A job carrying its own
`permissions:` block replaces the inherited set entirely — so adding the grant at
the top while `detect-changes` (or a job added later) declares its own would leave
`dorny/paths-filter` exactly as unable to read the pull request as before.

This acceptance therefore resolves the EFFECTIVE permissions of the job that
invokes the filter, the way GitHub does, rather than checking that the string
appears somewhere in the file.

It also pins the consequence the operator cares about: the jobs the filter gates
are reachable, so a filtered run produces verdicts instead of the row of skips
that made CI look green while nothing had been validated.

Phase RED: no permissions exist to resolve.
Phase GREEN: the filter job's effective permissions include pull-requests: read.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.commands.initializer import ProjectInitializer

pytestmark = [pytest.mark.coach]

FILTER_ACTION = "dorny/paths-filter"


def _generated_workflow(tmp_path: Path) -> dict:
    cfg = tmp_path / ".atdd"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    ProjectInitializer(target_dir=tmp_path)._write_workflow(repo="owner/repo")
    path = tmp_path / ".github" / "workflows" / "atdd-validate.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _effective_permissions(doc: dict, job_name: str) -> dict:
    """Permissions GitHub actually applies to ``job_name``.

    A job-level block REPLACES the workflow-level one rather than merging with it,
    which is the whole reason this is resolved rather than grepped.
    """
    job = doc["jobs"][job_name]
    if "permissions" in job:
        return job["permissions"] or {}
    return doc.get("permissions") or {}


def _job_running_the_filter(doc: dict) -> str:
    for name, job in doc.get("jobs", {}).items():
        for step in job.get("steps") or []:
            if FILTER_ACTION in str(step.get("uses", "")):
                return name
    raise AssertionError(f"no generated job runs {FILTER_ACTION}")


def test_c025_unit_002_the_change_filter_job_can_read_pull_request_files(tmp_path):
    doc = _generated_workflow(tmp_path)
    filter_job = _job_running_the_filter(doc)

    effective = _effective_permissions(doc, filter_job)
    assert effective.get("pull-requests") == "read", (
        f"job {filter_job!r} runs {FILTER_ACTION}, which calls the pull-request "
        f"files API, but its effective permissions are {effective or '(inherited default)'} "
        "— the call is refused and every job it gates skips"
    )
    assert effective.get("contents") == "read", (
        f"job {filter_job!r} checks out the repo and cannot read it"
    )


def test_c025_unit_002_the_jobs_the_filter_gates_are_reachable(tmp_path):
    """A filter nobody depends on would satisfy the grant and validate nothing."""
    doc = _generated_workflow(tmp_path)
    filter_job = _job_running_the_filter(doc)

    gated = [
        name for name, job in doc["jobs"].items()
        if filter_job in (job.get("needs") or [])
    ]
    assert gated, (
        f"no job depends on {filter_job!r}, so its verdict gates nothing and the "
        "permission would be granted for a filter with no consequence"
    )
    for name in gated:
        assert doc["jobs"][name].get("if"), (
            f"job {name!r} is gated by {filter_job!r} but carries no condition "
            "reading its outputs"
        )
