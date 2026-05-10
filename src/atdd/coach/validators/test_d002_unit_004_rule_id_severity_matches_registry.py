# URN: test:review-phase-boundaries:review-report-schema:D002-UNIT-004-rule-id-severity-matches-registry
# Acceptance: acc:review-phase-boundaries:D002-UNIT-004-rule-id-severity-matches-registry
# WMBT: wmbt:review-phase-boundaries:D002
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""
D002-UNIT-004 — When ``rule_id != null``, the finding's ``severity`` and
``disposition`` MUST match the registry binding from ``bind_rule(rule_id)``.
Mismatches are rejected at intake.

Phase RED: fails because the intake validator does not exist yet.
Phase GREEN: intake validator rejects mismatches and accepts conforming reports.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import atdd

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
FIXTURES_DIR = ATDD_PKG_DIR / "coach" / "schemas" / "fixtures" / "review-report"


def _load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    assert path.exists(), f"Fixture not found: {path}"
    with path.open() as fh:
        return json.load(fh)


def test_negative_fixture_exists() -> None:
    """The negative fixture (severity mismatch) is committed."""
    path = FIXTURES_DIR / "negative-severity-mismatch.json"
    assert path.exists(), (
        f"Missing negative fixture: {path}. "
        f"Acceptance D002-UNIT-004 requires a fixture triggering hard rule 3."
    )


def test_severity_mismatch_rejected() -> None:
    """Intake rejects a finding with wrong severity/disposition for a known rule_id."""
    from atdd.coach.utils.review_report_intake import validate_review_report

    report = _load_fixture("negative-severity-mismatch.json")
    result = validate_review_report(report, skip_schema=True)

    assert not result.valid, (
        "Intake should reject a report with rule_id severity/disposition mismatch."
    )
    hard_rule_3_errors = [e for e in result.errors if e.rule == "hard-rule-3"]
    assert hard_rule_3_errors, (
        "Expected at least one hard-rule-3 error. "
        f"Got errors: {result.error_messages}"
    )
    error_msg = hard_rule_3_errors[0].message
    # Must cite the rule_id.
    assert "coder.logging.coach-silent-swallow" in error_msg, (
        f"Error must cite the rule_id: {error_msg}"
    )
    # Must mention registry-expected values.
    assert "registry" in error_msg.lower(), (
        f"Error must mention registry expectations: {error_msg}"
    )


def test_conforming_rule_id_accepted() -> None:
    """Intake accepts a finding with registry-matching severity/disposition."""
    from atdd.coach.utils.review_report_intake import validate_review_report

    # coder.logging.coach-silent-swallow has severity=4, disposition=suppress-and-clean
    report = {
        "review_id": "rev-conforming",
        "target_commit": "abc1234",
        "reviewer_agent_id": "reviewer-v9-no-write",
        "wmbt_urn": "wmbt:review-phase-boundaries:D002",
        "phase": "GREEN",
        "verdict": "concern",
        "tier1_risk_score": 4,
        "findings": [
            {
                "rule_id": "coder.logging.coach-silent-swallow",
                "severity": 4,
                "disposition": "suppress-and-clean",
                "surface": "convention",
                "location": "test.py:1",
                "acceptance_ref": "acc:review-phase-boundaries:D002-UNIT-004-rule-id-severity-matches-registry",
                "description": "Conforming finding with registry-matching values.",
                "evidence": "Evidence here.",
            }
        ],
        "ac_coverage": {
            "acc:review-phase-boundaries:D002-UNIT-004-rule-id-severity-matches-registry": "covered",
        },
        "summary": "Conforming report — should be accepted.",
    }
    result = validate_review_report(report, skip_schema=True)
    assert result.valid, (
        f"Conforming report should be accepted. Errors: {result.error_messages}"
    )


def test_null_rule_id_accepted() -> None:
    """Intake accepts a finding with rule_id=null (LLM-only finding)."""
    from atdd.coach.utils.review_report_intake import validate_review_report

    report = {
        "review_id": "rev-null-rule-id",
        "target_commit": "abc1234",
        "reviewer_agent_id": "reviewer-v9-no-write",
        "wmbt_urn": "wmbt:review-phase-boundaries:D002",
        "phase": "GREEN",
        "verdict": "concern",
        "tier1_risk_score": 2,
        "findings": [
            {
                "rule_id": None,
                "severity": 2,
                "surface": "semantic",
                "location": "test.py:1",
                "acceptance_ref": "acc:review-phase-boundaries:D002-UNIT-004-rule-id-severity-matches-registry",
                "description": "LLM-only finding with null rule_id.",
                "evidence": "No registered rule maps to this.",
            }
        ],
        "ac_coverage": {
            "acc:review-phase-boundaries:D002-UNIT-004-rule-id-severity-matches-registry": "partial",
        },
        "summary": "LLM-only finding — should be accepted.",
    }
    result = validate_review_report(report, skip_schema=True)
    assert result.valid, (
        f"Null rule_id finding should be accepted. Errors: {result.error_messages}"
    )
