# URN: test:review-phase-boundaries:E002-UNIT-005-output-json
# Acceptance: acc:review-phase-boundaries:E002-UNIT-005-output-json
# WMBT: wmbt:review-phase-boundaries:E002
# Phase: RED
# Layer: unit

"""E002-UNIT-005 — --output json prints the validated review-report payload.

When --output json is passed, the full validated review-report dict is
printed as JSON to stdout instead of the human-readable summary.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.platform]


def _pass_report() -> dict:
    return {
        "review_id": str(uuid.uuid4()),
        "target_commit": "beefcafe12345678",
        "reviewer_agent_id": "reviewer-json-test",
        "wmbt_urn": "wmbt:review-phase-boundaries:E002",
        "phase": "GREEN",
        "verdict": "pass",
        "tier1_risk_score": 0,
        "findings": [],
        "ac_coverage": {},
        "summary": "All good.",
    }


@pytest.fixture()
def runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / ".atdd" / "runtime"
    root.mkdir(parents=True)
    return root


def test_output_json_flag_prints_valid_json(runtime_root: Path, capsys) -> None:
    """--output json writes parseable JSON to stdout."""
    from atdd.coach.commands import judge as judge_mod
    from atdd.coach.commands.coach_review import run_review

    report = _pass_report()
    original_registry = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY["claude-sonnet-4-6"] = lambda: None  # type: ignore[assignment]
    try:
        with (
            patch(
                "atdd.coach.commands.coach_review._spawn_reviewer_agent",
                return_value="reviewer-json-001",
            ),
            patch(
                "atdd.coach.commands.coach_review._wait_for_report",
                return_value=report,
            ),
            patch.dict("os.environ", {"ATDD_RUNTIME_ROOT": str(runtime_root)}),
        ):
            rc = run_review(["--commit", "beefcafe12345678", "--output", "json"])
    finally:
        judge_mod.LLM_REGISTRY.clear()
        judge_mod.LLM_REGISTRY.update(original_registry)

    assert rc == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert isinstance(parsed, dict)


def test_output_json_contains_required_fields(runtime_root: Path, capsys) -> None:
    """--output json payload contains review_id, verdict, and summary."""
    from atdd.coach.commands import judge as judge_mod
    from atdd.coach.commands.coach_review import run_review

    report = _pass_report()
    original_registry = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY["claude-sonnet-4-6"] = lambda: None  # type: ignore[assignment]
    try:
        with (
            patch(
                "atdd.coach.commands.coach_review._spawn_reviewer_agent",
                return_value="reviewer-json-002",
            ),
            patch(
                "atdd.coach.commands.coach_review._wait_for_report",
                return_value=report,
            ),
            patch.dict("os.environ", {"ATDD_RUNTIME_ROOT": str(runtime_root)}),
        ):
            run_review(["--commit", "beefcafe12345678", "--output", "json"])
    finally:
        judge_mod.LLM_REGISTRY.clear()
        judge_mod.LLM_REGISTRY.update(original_registry)

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["review_id"] == report["review_id"]
    assert parsed["verdict"] == "pass"
    assert parsed["summary"] == "All good."


def test_default_output_is_text_not_json(runtime_root: Path, capsys) -> None:
    """Without --output json, stdout is human-readable text, not JSON."""
    from atdd.coach.commands import judge as judge_mod
    from atdd.coach.commands.coach_review import run_review

    report = _pass_report()
    original_registry = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY["claude-sonnet-4-6"] = lambda: None  # type: ignore[assignment]
    try:
        with (
            patch(
                "atdd.coach.commands.coach_review._spawn_reviewer_agent",
                return_value="reviewer-text-001",
            ),
            patch(
                "atdd.coach.commands.coach_review._wait_for_report",
                return_value=report,
            ),
            patch.dict("os.environ", {"ATDD_RUNTIME_ROOT": str(runtime_root)}),
        ):
            run_review(["--commit", "beefcafe12345678"])
    finally:
        judge_mod.LLM_REGISTRY.clear()
        judge_mod.LLM_REGISTRY.update(original_registry)

    captured = capsys.readouterr()
    try:
        json.loads(captured.out)
        is_json = True
    except (json.JSONDecodeError, ValueError):
        is_json = False

    assert not is_json, "Default output should not be JSON"
