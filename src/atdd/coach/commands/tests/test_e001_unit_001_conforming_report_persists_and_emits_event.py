# URN: test:review-phase-boundaries:review-phase-boundaries:E001-UNIT-001-conforming-report-persists-and-emits-event
# Acceptance: acc:review-phase-boundaries:E001-UNIT-001-conforming-report-persists-and-emits-event
# WMBT: plan/review_phase_boundaries/E001.yaml
# Phase: RED
# Layer: application
"""E001-UNIT-001 — Conforming review report is persisted and emits a
``review_complete`` event.

Given:
  - An agent process tagged persona=reviewer is registered under
    ``.atdd/runtime/agents/<reviewer-id>/``.
  - A conforming review-report file exists at the path passed to
    ``--report-file``.

When:
  - The reviewer invokes ``atdd agent review --target-commit <sha>
    --report-file <path>``.

Then:
  - The report is validated against ``review-report.schema.json`` plus the
    three cross-field hard rules.
  - The validated report is written to
    ``.atdd/runtime/agents/<reviewer-id>/reviews/<review-id>.json``.
  - A ``review_complete`` event conforming to ``runtime-event.schema.json``
    is appended to ``.atdd/runtime/agents/<reviewer-id>/events.jsonl``.
  - The command exits 0.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

import atdd

pytestmark = [pytest.mark.platform]

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
RUNTIME_EVENT_SCHEMA = (
    ATDD_PKG_DIR / "coach" / "schemas" / "runtime-event.schema.json"
)
FIXTURES_DIR = (
    ATDD_PKG_DIR / "coach" / "schemas" / "fixtures" / "review-report"
)


@pytest.fixture
def runtime_root(tmp_path: Path) -> Path:
    return tmp_path / ".atdd" / "runtime"


@pytest.fixture
def reviewer_agent_id() -> str:
    return "reviewer-530-001"


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
    """Copy a fixture file into tmp_path and return its path."""
    src = FIXTURES_DIR / fixture_name
    dst = tmp_path / fixture_name
    dst.write_text(src.read_text())
    return dst


# ---------------------------------------------------------------------------
# Pass-clean report persists and emits review_complete event
# ---------------------------------------------------------------------------


def test_pass_clean_report_persists_and_emits_event(
    runtime_root: Path, reviewer_agent_id: str, reviewer_manifest: Path,
    tmp_path: Path,
):
    """A conforming pass report is validated, persisted under reviews/,
    and a review_complete event is appended to events.jsonl."""
    from atdd.coach.commands import agent

    report_path = _write_report_fixture(tmp_path, "pass-clean.json")
    report_data = json.loads(report_path.read_text())

    result_path = agent.cmd_review(
        target_commit="abc1234",
        report_file=str(report_path),
        agent_id=reviewer_agent_id,
        runtime_root=runtime_root,
    )

    # The review file is written at reviews/<review_id>.json
    reviews_dir = runtime_root / "agents" / reviewer_agent_id / "reviews"
    assert result_path.parent == reviews_dir
    assert result_path.is_file()

    # The persisted report matches the original report data
    persisted = json.loads(result_path.read_text())
    assert persisted["review_id"] == report_data["review_id"]
    assert persisted["verdict"] == "pass"
    assert persisted["target_commit"] == report_data["target_commit"]

    # A review_complete event was appended to events.jsonl
    events_path = runtime_root / "agents" / reviewer_agent_id / "events.jsonl"
    assert events_path.is_file()
    lines = [ln for ln in events_path.read_text().splitlines() if ln.strip()]
    assert len(lines) >= 1

    event = json.loads(lines[-1])
    schema = json.loads(RUNTIME_EVENT_SCHEMA.read_text())
    jsonschema.validate(event, schema)
    assert event["event_type"] == "review_complete"
    assert event["agent_id"] == reviewer_agent_id
    assert event["payload"]["review_id"] == report_data["review_id"]


# ---------------------------------------------------------------------------
# Concern report persists and emits review_complete event
# ---------------------------------------------------------------------------


def test_concern_report_persists_and_emits_event(
    runtime_root: Path, reviewer_agent_id: str, reviewer_manifest: Path,
    tmp_path: Path,
):
    """A conforming concern report is validated and persisted."""
    from atdd.coach.commands import agent

    report_path = _write_report_fixture(tmp_path, "concern.json")
    report_data = json.loads(report_path.read_text())

    result_path = agent.cmd_review(
        target_commit="abc1234",
        report_file=str(report_path),
        agent_id=reviewer_agent_id,
        runtime_root=runtime_root,
    )
    assert result_path.is_file()

    persisted = json.loads(result_path.read_text())
    assert persisted["verdict"] == "concern"
    assert persisted["review_id"] == report_data["review_id"]

    events_path = runtime_root / "agents" / reviewer_agent_id / "events.jsonl"
    event = json.loads(events_path.read_text().splitlines()[-1])
    assert event["event_type"] == "review_complete"


# ---------------------------------------------------------------------------
# Fail report persists and emits review_complete event
# ---------------------------------------------------------------------------


def test_fail_report_persists_and_emits_event(
    runtime_root: Path, reviewer_agent_id: str, reviewer_manifest: Path,
    tmp_path: Path,
):
    """A conforming fail report is validated and persisted."""
    from atdd.coach.commands import agent

    report_path = _write_report_fixture(tmp_path, "fail.json")
    report_data = json.loads(report_path.read_text())

    result_path = agent.cmd_review(
        target_commit="abc1234",
        report_file=str(report_path),
        agent_id=reviewer_agent_id,
        runtime_root=runtime_root,
    )
    assert result_path.is_file()

    persisted = json.loads(result_path.read_text())
    assert persisted["verdict"] == "fail"
    assert persisted["review_id"] == report_data["review_id"]

    events_path = runtime_root / "agents" / reviewer_agent_id / "events.jsonl"
    event = json.loads(events_path.read_text().splitlines()[-1])
    assert event["event_type"] == "review_complete"


# ---------------------------------------------------------------------------
# Minimal report persists (smallest valid report)
# ---------------------------------------------------------------------------


def test_minimal_report_persists_and_emits_event(
    runtime_root: Path, reviewer_agent_id: str, reviewer_manifest: Path,
    tmp_path: Path,
):
    """A minimal conforming report (required fields only) is persisted."""
    from atdd.coach.commands import agent

    report_path = _write_report_fixture(tmp_path, "minimal.json")
    report_data = json.loads(report_path.read_text())

    result_path = agent.cmd_review(
        target_commit="abc1234",
        report_file=str(report_path),
        agent_id=reviewer_agent_id,
        runtime_root=runtime_root,
    )
    assert result_path.is_file()

    persisted = json.loads(result_path.read_text())
    assert persisted["review_id"] == report_data["review_id"]


# ---------------------------------------------------------------------------
# Non-reviewer persona is rejected
# ---------------------------------------------------------------------------


def test_non_reviewer_persona_rejected(
    runtime_root: Path, tmp_path: Path,
):
    """A non-reviewer agent cannot invoke atdd agent review."""
    from atdd.coach.commands import agent

    coder_id = "coder-530-001"
    agent_dir = runtime_root / "agents" / coder_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    manifest = agent_dir / "manifest.json"
    manifest.write_text(json.dumps({"persona": "coder", "agent_id": coder_id}))

    report_path = _write_report_fixture(tmp_path, "pass-clean.json")

    with pytest.raises(ValueError, match="[Rr]eviewer|persona"):
        agent.cmd_review(
            target_commit="abc1234",
            report_file=str(report_path),
            agent_id=coder_id,
            runtime_root=runtime_root,
        )

    # No review file written
    reviews_dir = runtime_root / "agents" / coder_id / "reviews"
    assert not reviews_dir.exists() or not list(reviews_dir.iterdir())

    # No event emitted
    events_path = runtime_root / "agents" / coder_id / "events.jsonl"
    assert not events_path.exists()


# ---------------------------------------------------------------------------
# No manifest = rejected (persona must be explicit)
# ---------------------------------------------------------------------------


def test_no_manifest_rejected(
    runtime_root: Path, tmp_path: Path,
):
    """An agent without a manifest.json cannot invoke atdd agent review.
    Persona must be explicitly set to reviewer."""
    from atdd.coach.commands import agent

    bare_id = "bare-agent-001"
    # Intentionally do NOT create manifest.json

    report_path = _write_report_fixture(tmp_path, "pass-clean.json")

    with pytest.raises(ValueError, match="[Rr]eviewer|persona"):
        agent.cmd_review(
            target_commit="abc1234",
            report_file=str(report_path),
            agent_id=bare_id,
            runtime_root=runtime_root,
        )
