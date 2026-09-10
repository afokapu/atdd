# URN: test:govern-lifecycle:issue-body-contract-has-one-reader:E076-SMOKE-001-the-real-authoring-cli-emits-an-accepted-body
# Acceptance: acc:govern-lifecycle:E076-SMOKE-001-the-real-authoring-cli-emits-an-accepted-body
# WMBT: wmbt:govern-lifecycle:E076
# Phase: SMOKE
# Layer: integration
"""E076-SMOKE-001 — the real authoring CLI emits a body the validator accepts (#1901).

The UNIT test calls `create_issue_body` in-process. This one runs the installed
CLI as a subprocess, because the defect was operator-visible: `atdd author issue`
created issues that the repository's own validators then rejected, 38 of 40 of
them, for a section the schema never required.

Asserts on the body the CLI actually rendered, put to the validator's reader —
the two ends of the contract, over the real artifact between them.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from atdd.coach.validators.test_issue_validation import check_body_sections

pytestmark = [pytest.mark.platform]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]


@pytest.fixture(scope="module")
def rendered() -> str:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    result = subprocess.run(
        [sys.executable, "-m", "atdd", "author", "issue",
         "--title", "E076 smoke probe", "--slug", "e076-smoke-probe", "--dry-run"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "## Issue Metadata" in result.stdout, (
        f"the CLI rendered no issue body:\n{result.stdout[:600]}"
    )
    return result.stdout


def test_the_validator_accepts_the_bodies_the_cli_emits(rendered: str) -> None:
    """THE POINT: this was false for every issue in the repository."""
    missing = check_body_sections(rendered)
    assert missing == [], (
        "the authoring CLI emits a body its own repository rejects, missing: "
        f"{missing}"
    )


def test_the_dry_run_creates_nothing() -> None:
    assert not (REPO_ROOT / "plan" / "e076-smoke-probe.yaml").exists()
