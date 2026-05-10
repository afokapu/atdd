# URN: test:review-phase-boundaries:review-report-schema:D002-UNIT-002-pass-blocked-when-ac-not-covered
# Acceptance: acc:review-phase-boundaries:D002-UNIT-002-pass-blocked-when-ac-not-covered
# WMBT: wmbt:review-phase-boundaries:D002
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""
D002-UNIT-002 — A review report with ``verdict: pass`` AND any
``ac_coverage[*] == not_covered`` is rejected at coach intake with an
error citing the offending acceptance_ref(s).

Phase RED: fails because the intake validator does not exist yet.
Phase GREEN: intake validator rejects the malformed report.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import atdd

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
FIXTURES_DIR = ATDD_PKG_DIR / "coach" / "schemas" / "fixtures" / "review-report"

NEGATIVE_FIXTURE = FIXTURES_DIR / "negative-pass-with-not-covered.json"


def _load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    assert path.exists(), f"Fixture not found: {path}"
    with path.open() as fh:
        return json.load(fh)


def test_negative_fixture_exists() -> None:
    """The negative fixture (pass + not_covered) is committed."""
    assert NEGATIVE_FIXTURE.exists(), (
        f"Missing negative fixture: {NEGATIVE_FIXTURE}. "
        f"Acceptance D002-UNIT-002 requires a fixture triggering hard rule 1."
    )


def test_pass_blocked_when_ac_not_covered() -> None:
    """Intake rejects verdict=pass when any ac_coverage entry is not_covered."""
    from atdd.coach.utils.review_report_intake import validate_review_report

    report = _load_fixture("negative-pass-with-not-covered.json")
    result = validate_review_report(report, skip_schema=True)

    assert not result.valid, (
        "Intake should reject a pass verdict when ACs are not_covered."
    )
    hard_rule_1_errors = [e for e in result.errors if e.rule == "hard-rule-1"]
    assert hard_rule_1_errors, (
        "Expected at least one hard-rule-1 error. "
        f"Got errors: {result.error_messages}"
    )
    error_msg = hard_rule_1_errors[0].message
    assert "not_covered" in error_msg, (
        f"Error message must mention 'not_covered': {error_msg}"
    )
    # Must name the offending acceptance_ref.
    assert "D002-UNIT-002" in error_msg, (
        f"Error must name the offending acceptance_ref: {error_msg}"
    )


def test_pass_accepted_when_all_covered() -> None:
    """Intake accepts a clean pass report (all ACs covered)."""
    from atdd.coach.utils.review_report_intake import validate_review_report

    report = _load_fixture("pass-clean.json")
    result = validate_review_report(report, skip_schema=True)

    assert result.valid, (
        f"Clean pass report should be accepted. Errors: {result.error_messages}"
    )


def test_fail_verdict_with_not_covered_accepted() -> None:
    """Intake accepts a fail verdict even when ACs are not_covered."""
    from atdd.coach.utils.review_report_intake import validate_review_report

    report = _load_fixture("fail.json")
    result = validate_review_report(report, skip_schema=True)

    assert result.valid, (
        f"Fail verdict with not_covered ACs should pass hard-rule-1 check. "
        f"Errors: {result.error_messages}"
    )
