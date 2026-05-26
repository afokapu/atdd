# URN: test:govern-lifecycle:close-substrate-friction-regressions:E024-SMOKE-001-merge-produces-exactly-one-publish-success
# Acceptance: acc:govern-lifecycle:E024-SMOKE-001-merge-produces-exactly-one-publish-success
# WMBT: wmbt:govern-lifecycle:E024
# Phase: SMOKE
# Layer: backend.integration
"""
AC-SMOKE-001: after merging a PR to main, the Publish workflow produces exactly one
workflow_run success and zero workflow_run skips in the 5-minute window following the merge.

RED state: This test is a structural stub that verifies the YAML conditions are in
place. The full end-to-end SMOKE (polling gh run list after a real merge) requires a
live GitHub environment and is intended for post-merge CI verification, not local runs.
This structural stub drives the implementation and confirms the conditions are present.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.slow]

REPO_ROOT = Path(__file__).resolve().parents[6]
VALIDATE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "atdd-validate.yml"
PUBLISH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish.yml"


def test_publish_smoke_structural_preconditions():
    """AC-SMOKE-001 (structural): both workflow fixes must be in place for zero-skip merges."""
    import yaml

    validate_text = VALIDATE_WORKFLOW.read_text(encoding="utf-8")
    publish_text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

    doc = yaml.safe_load(validate_text)
    on_block = doc.get("on", doc.get(True, {}))
    validate_ok = "issues" not in on_block
    publish_ok = "head_branch == 'main'" in publish_text

    errors = []
    if not validate_ok:
        errors.append(
            "atdd-validate.yml still has 'issues:' trigger — "
            "each issues-event fires a Publish:skipped run (issue #845 Item C)."
        )
    if not publish_ok:
        errors.append(
            "publish.yml missing 'head_branch == \"main\"' — "
            "belt-and-suspenders guard absent (issue #845 Item C)."
        )

    assert not errors, (
        "SMOKE pre-conditions not met — zero-skip merge guarantee cannot hold:\n"
        + "\n".join(f"  • {e}" for e in errors)
    )
