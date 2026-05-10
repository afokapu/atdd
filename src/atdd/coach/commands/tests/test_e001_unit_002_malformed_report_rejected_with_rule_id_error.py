# URN: test:review-phase-boundaries:review-phase-boundaries:E001-UNIT-002-malformed-report-rejected-with-rule-id-error
# Acceptance: acc:review-phase-boundaries:E001-UNIT-002-malformed-report-rejected-with-rule-id-error
# WMBT: plan/review_phase_boundaries/E001.yaml
# Phase: RED
# Layer: application
"""E001-UNIT-002 — Malformed review report is rejected with a rule-ID'd
error; nothing is written and no event is emitted.

Covers:
  - Hard rule 1: verdict=pass with ac_coverage entry not_covered
  - Hard rule 2: verdict=pass with strict rule_id-bound finding
  - Hard rule 3: severity/disposition mismatch with registry
  - Schema validation failure (missing required fields)
  - Non-JSON-parseable file
  - Missing report file
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import atdd

pytestmark = [pytest.mark.platform]

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
FIXTURES_DIR = (
    ATDD_PKG_DIR / "coach" / "schemas" / "fixtures" / "review-report"
)


@pytest.fixture
def runtime_root(tmp_path: Path) -> Path:
    return tmp_path / ".atdd" / "runtime"


@pytest.fixture
def reviewer_agent_id() -> str:
    return "reviewer-530-002"


@pytest.fixture
def reviewer_manifest(
    runtime_root: Path, reviewer_agent_id: str,
) -> Path:
    agent_dir = runtime_root / "agents" / reviewer_agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    manifest = agent_dir / "manifest.json"
    manifest.write_text(json.dumps({
        "persona": "reviewer",
        "agent_id": reviewer_agent_id,
    }))
    return manifest


def _write_report_fixture(tmp_path: Path, fixture_name: str) -> Path:
    src = FIXTURES_DIR / fixture_name
    dst = tmp_path / fixture_name
    dst.write_text(src.read_text())
    return dst


def _assert_no_side_effects(runtime_root: Path, reviewer_agent_id: str):
    """After a rejection, no review file or event should exist."""
    reviews_dir = runtime_root / "agents" / reviewer_agent_id / "reviews"
    assert not reviews_dir.exists() or not list(reviews_dir.iterdir())
    events_path = runtime_root / "agents" / reviewer_agent_id / "events.jsonl"
    assert not events_path.exists()


# ---------------------------------------------------------------------------
# Hard rule 1: pass verdict with not_covered AC
# ---------------------------------------------------------------------------


def test_hard_rule_1_pass_with_not_covered_rejected(
    runtime_root: Path, reviewer_agent_id: str, reviewer_manifest: Path,
    tmp_path: Path,
):
    """verdict=pass with ac_coverage not_covered is rejected with hard-rule-1
    error. No file is written; no event is emitted."""
    from atdd.coach.commands import agent

    report_path = _write_report_fixture(
        tmp_path, "negative-pass-with-not-covered.json",
    )

    with pytest.raises(ValueError, match="hard-rule-1") as exc_info:
        agent.cmd_review(
            target_commit="abc1234",
            report_file=str(report_path),
            agent_id=reviewer_agent_id,
            runtime_root=runtime_root,
        )
    # Error cites the offending field
    assert "not_covered" in str(exc_info.value)

    _assert_no_side_effects(runtime_root, reviewer_agent_id)


# ---------------------------------------------------------------------------
# Hard rule 2: pass verdict with strict finding
# ---------------------------------------------------------------------------


def test_hard_rule_2_pass_with_strict_finding_rejected(
    runtime_root: Path, reviewer_agent_id: str, reviewer_manifest: Path,
    tmp_path: Path,
):
    """verdict=pass with a strict rule_id-bound finding is rejected with
    hard-rule-2 error."""
    from atdd.coach.commands import agent

    report_path = _write_report_fixture(
        tmp_path, "negative-pass-with-strict-finding.json",
    )

    with pytest.raises(ValueError, match="hard-rule-2") as exc_info:
        agent.cmd_review(
            target_commit="abc1234",
            report_file=str(report_path),
            agent_id=reviewer_agent_id,
            runtime_root=runtime_root,
        )
    assert "strict" in str(exc_info.value).lower()

    _assert_no_side_effects(runtime_root, reviewer_agent_id)


# ---------------------------------------------------------------------------
# Hard rule 3: severity/disposition mismatch with registry
# ---------------------------------------------------------------------------


def test_hard_rule_3_severity_mismatch_rejected(
    runtime_root: Path, reviewer_agent_id: str, reviewer_manifest: Path,
    tmp_path: Path,
):
    """A finding with severity/disposition diverging from the registry is
    rejected with hard-rule-3 error."""
    from atdd.coach.commands import agent

    report_path = _write_report_fixture(
        tmp_path, "negative-severity-mismatch.json",
    )

    with pytest.raises(ValueError, match="hard-rule-3") as exc_info:
        agent.cmd_review(
            target_commit="abc1234",
            report_file=str(report_path),
            agent_id=reviewer_agent_id,
            runtime_root=runtime_root,
        )
    # Error includes the rule_id and registry-expected values
    err_text = str(exc_info.value)
    assert "coder.logging.coach-silent-swallow" in err_text
    assert "registry" in err_text.lower()

    _assert_no_side_effects(runtime_root, reviewer_agent_id)


# ---------------------------------------------------------------------------
# Schema validation failure: missing required fields
# ---------------------------------------------------------------------------


def test_schema_validation_failure_rejected(
    runtime_root: Path, reviewer_agent_id: str, reviewer_manifest: Path,
    tmp_path: Path,
):
    """A report missing required fields is rejected with a schema error."""
    from atdd.coach.commands import agent

    # Write a report missing required fields
    bad_report = tmp_path / "missing-fields.json"
    bad_report.write_text(json.dumps({"review_id": "rev-incomplete"}))

    with pytest.raises(ValueError, match="schema") as exc_info:
        agent.cmd_review(
            target_commit="abc1234",
            report_file=str(bad_report),
            agent_id=reviewer_agent_id,
            runtime_root=runtime_root,
        )
    # Error references the missing field or schema path
    err_text = str(exc_info.value).lower()
    assert "required" in err_text or "schema" in err_text

    _assert_no_side_effects(runtime_root, reviewer_agent_id)


# ---------------------------------------------------------------------------
# Non-JSON-parseable file
# ---------------------------------------------------------------------------


def test_non_json_file_rejected(
    runtime_root: Path, reviewer_agent_id: str, reviewer_manifest: Path,
    tmp_path: Path,
):
    """A non-JSON file is rejected with a parse error."""
    from atdd.coach.commands import agent

    bad_file = tmp_path / "report.txt"
    bad_file.write_text("This is not JSON at all.")

    with pytest.raises((ValueError, json.JSONDecodeError)):
        agent.cmd_review(
            target_commit="abc1234",
            report_file=str(bad_file),
            agent_id=reviewer_agent_id,
            runtime_root=runtime_root,
        )

    _assert_no_side_effects(runtime_root, reviewer_agent_id)


# ---------------------------------------------------------------------------
# Missing report file
# ---------------------------------------------------------------------------


def test_missing_report_file_rejected(
    runtime_root: Path, reviewer_agent_id: str, reviewer_manifest: Path,
    tmp_path: Path,
):
    """A non-existent report file path is rejected with FileNotFoundError."""
    from atdd.coach.commands import agent

    with pytest.raises(FileNotFoundError):
        agent.cmd_review(
            target_commit="abc1234",
            report_file=str(tmp_path / "nonexistent.json"),
            agent_id=reviewer_agent_id,
            runtime_root=runtime_root,
        )

    _assert_no_side_effects(runtime_root, reviewer_agent_id)
