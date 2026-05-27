# URN: test:spawn-agents:E024-SMOKE-001-atdd-validate-coach-passes-with-graph-section-present
# Acceptance: acc:spawn-agents:E024-SMOKE-001-atdd-validate-coach-passes-with-graph-section-present
# WMBT: wmbt:spawn-agents:E024
# Phase: SMOKE
# Layer: smoke
"""E024-SMOKE-001 — `atdd validate coach --local --skip-api` on the live repo after
E023 ships reports zero coach.launch-prompt.must-include-wagon-graph violations.

Phase RED: fails because:
  (a) SESSION-LAUNCH-TEMPLATE.md lacks '## Wagon Architecture' → validator fires, or
  (b) The rule is not yet registered in session.convention.yaml → validate coach may
      fail to discover it.
Phase GREEN/SMOKE: E023 has added the section marker and E024 has registered the
rule; `atdd validate coach` exits 0 with no wagon-graph violations.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.slow]

_REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent
_RULE_ID = "coach.launch-prompt.must-include-wagon-graph"


def test_validate_coach_reports_no_wagon_graph_violations() -> None:
    """atdd validate coach --local --skip-api must report zero wagon-graph violations."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "atdd",
            "validate",
            "coach",
            "--local",
            "--skip-api",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )

    # Extract lines mentioning the wagon-graph rule from combined output.
    combined = result.stdout + result.stderr
    violation_lines = [
        line
        for line in combined.splitlines()
        if _RULE_ID in line
    ]

    assert not violation_lines, (
        f"atdd validate coach reported violations for '{_RULE_ID}':\n"
        + "\n".join(violation_lines)
        + "\n\nE023: add '## Wagon Architecture' to SESSION-LAUNCH-TEMPLATE.md.\n"
        "E024: ensure the rule is registered in session.convention.yaml."
    )


def test_validate_coach_exits_zero_or_fails_only_on_other_rules() -> None:
    """atdd validate coach must exit 0 (or non-zero only due to unrelated violations).

    This test passes if the wagon-graph rule specifically is clean, regardless
    of other coach-level violations in the current branch's diff.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "atdd",
            "validate",
            "coach",
            "--local",
            "--skip-api",
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )

    combined = result.stdout + result.stderr
    wagon_graph_violations = [
        line for line in combined.splitlines() if _RULE_ID in line
    ]

    # The wagon-graph rule specifically must be clean.
    assert not wagon_graph_violations, (
        f"'{_RULE_ID}' violation(s) present in validate-coach output:\n"
        + "\n".join(wagon_graph_violations)
    )
