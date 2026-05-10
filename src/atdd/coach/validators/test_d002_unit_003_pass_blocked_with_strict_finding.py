# URN: test:review-phase-boundaries:review-report-schema:D002-UNIT-003-pass-blocked-with-strict-finding
# Acceptance: acc:review-phase-boundaries:D002-UNIT-003-pass-blocked-with-strict-finding
# WMBT: wmbt:review-phase-boundaries:D002
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""
D002-UNIT-003 — A review report with ``verdict: pass`` AND one or more
findings carrying ``rule_id != null`` and ``disposition: strict`` is
rejected at coach intake.

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

NEGATIVE_FIXTURE = FIXTURES_DIR / "negative-pass-with-strict-finding.json"


def _load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    assert path.exists(), f"Fixture not found: {path}"
    with path.open() as fh:
        return json.load(fh)


def test_negative_fixture_exists() -> None:
    """The negative fixture (pass + strict finding) is committed."""
    assert NEGATIVE_FIXTURE.exists(), (
        f"Missing negative fixture: {NEGATIVE_FIXTURE}. "
        f"Acceptance D002-UNIT-003 requires a fixture triggering hard rule 2."
    )


def test_pass_blocked_with_strict_finding() -> None:
    """Intake rejects verdict=pass when a strict rule_id-bound finding exists."""
    from atdd.coach.utils.review_report_intake import validate_review_report

    report = _load_fixture("negative-pass-with-strict-finding.json")
    result = validate_review_report(report, skip_schema=True)

    assert not result.valid, (
        "Intake should reject a pass verdict with a strict rule_id-bound finding."
    )
    hard_rule_2_errors = [e for e in result.errors if e.rule == "hard-rule-2"]
    assert hard_rule_2_errors, (
        "Expected at least one hard-rule-2 error. "
        f"Got errors: {result.error_messages}"
    )
    error_msg = hard_rule_2_errors[0].message
    assert "strict" in error_msg.lower(), (
        f"Error message must mention 'strict': {error_msg}"
    )
    # Must name the offending rule_id.
    assert "coach.commit-trailers.phase-required" in error_msg, (
        f"Error must name the offending rule_id: {error_msg}"
    )


def test_concern_verdict_with_strict_finding_accepted() -> None:
    """Intake accepts a concern verdict even with a strict finding."""
    from atdd.coach.utils.review_report_intake import validate_review_report

    report = {
        "review_id": "rev-concern-strict",
        "target_commit": "abc1234",
        "reviewer_agent_id": "reviewer-v9-no-write",
        "wmbt_urn": "wmbt:review-phase-boundaries:D002",
        "phase": "GREEN",
        "verdict": "concern",
        "tier1_risk_score": 5,
        "findings": [
            {
                "rule_id": "coach.commit-trailers.phase-required",
                "severity": 4,
                "disposition": "strict",
                "surface": "convention",
                "location": "test.py:1",
                "acceptance_ref": "acc:review-phase-boundaries:D002-UNIT-003-pass-blocked-with-strict-finding",
                "description": "A strict finding with concern verdict.",
                "evidence": "Evidence here.",
            }
        ],
        "ac_coverage": {
            "acc:review-phase-boundaries:D002-UNIT-003-pass-blocked-with-strict-finding": "covered",
        },
        "summary": "Concern verdict with strict finding — should be accepted.",
    }
    result = validate_review_report(report, skip_schema=True)
    assert result.valid, (
        f"Concern verdict with strict finding should pass hard-rule-2 check. "
        f"Errors: {result.error_messages}"
    )
