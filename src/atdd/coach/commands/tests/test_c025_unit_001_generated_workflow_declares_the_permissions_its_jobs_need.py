# URN: test:govern-lifecycle:govern-lifecycle:C025-UNIT-001
# Acceptance: acc:govern-lifecycle:C025-UNIT-001-generated-workflow-declares-the-permissions-its-jobs-need
# WMBT: wmbt:govern-lifecycle:C025
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""C025 — the generated validate workflow must be able to read its own pull request.

`_write_workflow` emits a `detect-changes` job that runs `dorny/paths-filter`, and
that action calls the pull-request FILES API to decide which validate jobs run. The
generated workflow declares no `permissions:` at all, so it inherits the repository
default — and on a repository whose default token is read-contents-only, the call is
refused:

    detect-changes  ##[error]Resource not accessible by integration
    validate-coach  skipping   validate-coder  skipping   validate-planner  skipping

Measured on a real repo created by `gh repo create --private` and initialised by
`atdd init`: the first pull request it was ever asked to judge produced one failed
filter and a row of skips. Nothing was validated, and the only red check named a
third-party action rather than anything about the change.

This repo already found the same token limitation from the other end. Its own
`.github/workflows/atdd-validate.yml` carries a hand-added job-level block on
`validate-coach` explaining that "the repo default is `default_workflow_permissions:
read`, which grants the workflow token contents/packages/metadata only — NOT
pull-requests", added after PR #1692 passed vacuously in CI. That fix went to the
one job someone noticed; the GENERATED template every consumer gets never received
it, and `detect-changes` needs the same scope for the same reason.

Two acceptances because the two halves fail differently: UNIT-001 pins that the
grant is DECLARED, UNIT-002 that it REACHES the job making the call — a grant
declared where the filter cannot see it leaves the failure exactly where it was.

Phase RED: the generated workflow has no `permissions:` key anywhere.
Phase GREEN: it declares `contents: read` + `pull-requests: read`, and no more.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.commands.initializer import ProjectInitializer

pytestmark = [pytest.mark.coach]


def _generated_workflow(tmp_path: Path) -> dict:
    cfg = tmp_path / ".atdd"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")

    ProjectInitializer(target_dir=tmp_path)._write_workflow(repo="owner/repo")
    path = tmp_path / ".github" / "workflows" / "atdd-validate.yml"
    assert path.is_file(), "the initializer wrote no validate workflow"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_c025_unit_001_generated_workflow_declares_pull_requests_read(tmp_path):
    doc = _generated_workflow(tmp_path)

    perms = doc.get("permissions")
    assert perms is not None, (
        "the generated workflow declares no permissions at all, so it inherits "
        "the repository default — and a read-contents-only default makes "
        "dorny/paths-filter fail with 'Resource not accessible by integration'"
    )
    assert perms.get("pull-requests") == "read", (
        "the change filter calls the pull-request files API; without "
        "pull-requests: read the call is refused and every validate job skips"
    )
    assert perms.get("contents") == "read", (
        "checkout needs contents: read — declaring any permissions block at all "
        "drops every scope not named, so contents must be stated explicitly"
    )


def test_c025_unit_001_generated_workflow_grants_no_write_scope(tmp_path):
    """Least privilege: this workflow only ever reads."""
    doc = _generated_workflow(tmp_path)

    written = {k: v for k, v in (doc.get("permissions") or {}).items() if v == "write"}
    assert not written, (
        f"the validate workflow grants write scopes it never uses: {sorted(written)}"
    )
