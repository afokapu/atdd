# URN: test:review-phase-boundaries:reviewer-pr-ci-gate:E003-INTEGRATION-001-block-verdict-fails-the-workflow
# Acceptance: acc:review-phase-boundaries:E003-INTEGRATION-001-block-verdict-fails-the-workflow
# WMBT: wmbt:review-phase-boundaries:E003
# Phase: RED
# Layer: backend.integration
# Assertion: behavioral

"""E003-INTEGRATION-001 — when review-report.json contains verdict=fail,
the workflow's enforce-verdict shell fragment exits nonzero.

Extracts the enforce-verdict run: block from the workflow YAML, writes a
fixture report with verdict=fail, and executes the shell logic via
subprocess. Asserts exit code != 0.

Phase RED: fails because the workflow file does not yet exist.
Phase GREEN: workflow exists and the enforce-verdict logic exits 1 on fail.
"""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

pytestmark = [pytest.mark.coach]

REPO_ROOT = Path(__file__).resolve().parents[4]
WORKFLOW_FILE = REPO_ROOT / ".github" / "workflows" / "atdd-review.yml"


def _load_workflow() -> Dict[str, Any]:
    assert WORKFLOW_FILE.exists(), (
        f"Missing {WORKFLOW_FILE}. "
        "Acceptance E003-INTEGRATION-001 requires the workflow to exist."
    )
    with WORKFLOW_FILE.open() as fh:
        return yaml.safe_load(fh)


def _find_enforce_step_run(wf: Dict[str, Any]) -> str:
    """Return the run: block of the enforce-verdict step."""
    for job in wf.get("jobs", {}).values():
        for step in job.get("steps", []):
            run = step.get("run", "") or ""
            if "verdict" in run and ("exit 1" in run or "exit 0" in run):
                return run
    pytest.fail(
        "No enforce-verdict step found in the workflow. "
        "The step must read the verdict and exit nonzero on 'fail'."
    )


def _make_report(tmp_path: Path, verdict: str) -> Path:
    report = {
        "review_id": "test-review-001",
        "target_commit": "abc1234def",
        "reviewer_agent_id": "reviewer-test",
        "wmbt_urn": "wmbt:review-phase-boundaries:E003",
        "phase": "GREEN",
        "verdict": verdict,
        "tier1_risk_score": 0,
        "findings": [],
        "ac_coverage": {},
        "summary": f"Test report with verdict={verdict}.",
    }
    path = tmp_path / "review.json"
    path.write_text(json.dumps(report))
    return path


def test_fail_verdict_causes_nonzero_exit(tmp_path: pytest.TempPathFactory) -> None:
    """enforce-verdict shell logic MUST exit nonzero when verdict=fail."""
    wf = _load_workflow()
    enforce_run = _find_enforce_step_run(wf)

    report_path = _make_report(tmp_path, "fail")

    # Replace placeholder paths in the shell script with the fixture path.
    shell_script = enforce_run.replace("/tmp/review.json", str(report_path))

    result = subprocess.run(
        ["bash", "-e", "-c", shell_script],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        f"enforce-verdict shell logic MUST exit nonzero for verdict=fail. "
        f"Got exit code {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
