# URN: test:review-phase-boundaries:reviewer-pr-ci-gate:E003-INTEGRATION-002-annotate-verdict-passes-with-comment
# Acceptance: acc:review-phase-boundaries:E003-INTEGRATION-002-annotate-verdict-passes-with-comment
# WMBT: wmbt:review-phase-boundaries:E003
# Phase: RED
# Layer: backend.integration
# Assertion: behavioral

"""E003-INTEGRATION-002 — when review-report.json contains verdict=pass or
verdict=concern, the workflow's enforce-verdict shell fragment exits 0
(annotate-and-continue, not blocking).

Phase RED: fails because the workflow file does not yet exist.
Phase GREEN: workflow exists and the enforce-verdict logic exits 0 for
pass and concern verdicts.
"""

from __future__ import annotations

import json
import subprocess
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
        "Acceptance E003-INTEGRATION-002 requires the workflow to exist."
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
        "The step must read the verdict and exit 0 for pass/concern verdicts."
    )


def _make_report(tmp_path: Path, verdict: str) -> Path:
    report = {
        "review_id": "test-review-002",
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
    path = tmp_path / f"review_{verdict}.json"
    path.write_text(json.dumps(report))
    return path


def test_pass_verdict_causes_zero_exit(tmp_path: pytest.TempPathFactory) -> None:
    """enforce-verdict shell logic MUST exit 0 when verdict=pass."""
    wf = _load_workflow()
    enforce_run = _find_enforce_step_run(wf)

    report_path = _make_report(tmp_path, "pass")
    shell_script = enforce_run.replace("/tmp/review.json", str(report_path))

    result = subprocess.run(
        ["bash", "-c", shell_script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"enforce-verdict shell logic MUST exit 0 for verdict=pass. "
        f"Got exit code {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_concern_verdict_causes_zero_exit(tmp_path: pytest.TempPathFactory) -> None:
    """enforce-verdict shell logic MUST exit 0 when verdict=concern (annotate-and-continue)."""
    wf = _load_workflow()
    enforce_run = _find_enforce_step_run(wf)

    report_path = _make_report(tmp_path, "concern")
    shell_script = enforce_run.replace("/tmp/review.json", str(report_path))

    result = subprocess.run(
        ["bash", "-c", shell_script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"enforce-verdict shell logic MUST exit 0 for verdict=concern (annotate-and-continue). "
        f"Got exit code {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
