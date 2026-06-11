# URN: test:govern-lifecycle:decommission-projects-v2-board-sync:E053-UNIT-003-board-contract-regression-tests-retired
# Acceptance: acc:govern-lifecycle:E053-UNIT-003-board-contract-regression-tests-retired
# WMBT: wmbt:govern-lifecycle:E053
# Phase: RED
# Harness: unit
# Assertion: structural
# Layer: backend
"""E053-UNIT-003 — the 3 board-on regression tests are retired.

Post-removal contract: the board-contract regression tests encoding the old
"label swap AND project-field write" behaviour are gone, and no remaining test
asserts that update() runs a project-field write alongside the label swap.

RED now: the three named tests still exist in test_issue_update_fallback.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

RETIRED_TESTS = (
    "test_denied_logs_warning_with_remediation",
    "test_granted_runs_both_label_and_project_field",
    "test_non_matching_github_error_aborts",
)


def _tests_dir() -> Path:
    return Path(__file__).resolve().parent


def test_named_board_regression_tests_absent_from_collection():
    tests_dir = _tests_dir()
    offenders = []
    for path in tests_dir.glob("test_*.py"):
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in RETIRED_TESTS:
            if f"def {name}" in text:
                offenders.append(f"{path.name}: def {name}")
    assert not offenders, "retired board-contract tests still present:\n" + "\n".join(offenders)


def test_no_remaining_test_asserts_board_field_write_with_label():
    """No surviving test couples a label swap to a set_project_field_select call."""
    tests_dir = _tests_dir()
    offenders = []
    for path in tests_dir.glob("test_*.py"):
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "set_project_field_select.assert_called" in text:
            offenders.append(path.name)
    assert not offenders, "a test still asserts a board field write:\n" + "\n".join(offenders)
