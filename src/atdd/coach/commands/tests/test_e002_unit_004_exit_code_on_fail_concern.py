# URN: test:review-phase-boundaries:E002-UNIT-004-exit-code-on-fail-concern
# Acceptance: acc:review-phase-boundaries:E002-UNIT-004-exit-code-on-fail-concern
# WMBT: wmbt:review-phase-boundaries:E002
# Phase: RED
# Layer: unit

"""E002-UNIT-004 — exit codes per verdict (pass→0, fail→1, concern→2).

atdd coach review exits 0 on pass, 1 on fail, and 2 on concern so it
can be wired into a merge gate (nonzero blocks the merge).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.platform]


def _report(verdict: str) -> dict:
    return {
        "review_id": str(uuid.uuid4()),
        "target_commit": "aaabbbccc1234567",
        "reviewer_agent_id": "reviewer-exit-test",
        "wmbt_urn": "wmbt:review-phase-boundaries:E002",
        "phase": "GREEN",
        "verdict": verdict,
        "tier1_risk_score": 0,
        "findings": [],
        "ac_coverage": {},
        "summary": f"Verdict: {verdict}.",
    }


@pytest.fixture()
def runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / ".atdd" / "runtime"
    root.mkdir(parents=True)
    return root


@pytest.mark.parametrize("verdict,expected_rc", [
    ("pass", 0),
    ("fail", 1),
    ("concern", 2),
])
def test_exit_code_for_verdict(
    verdict: str, expected_rc: int, runtime_root: Path
) -> None:
    """Each verdict maps to the correct exit code."""
    from atdd.coach.commands import judge as judge_mod
    from atdd.coach.commands.coach_review import run_review

    report = _report(verdict)
    original_registry = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY["claude-sonnet-4-6"] = lambda: None  # type: ignore[assignment]
    try:
        with (
            patch(
                "atdd.coach.commands.coach_review._spawn_reviewer_agent",
                return_value="reviewer-exit-001",
            ),
            patch(
                "atdd.coach.commands.coach_review._wait_for_report",
                return_value=report,
            ),
            patch.dict("os.environ", {"ATDD_RUNTIME_ROOT": str(runtime_root)}),
        ):
            rc = run_review(["--commit", "aaabbbccc1234567"])
    finally:
        judge_mod.LLM_REGISTRY.clear()
        judge_mod.LLM_REGISTRY.update(original_registry)

    assert rc == expected_rc


def test_pass_verdict_prints_summary(runtime_root: Path, capsys) -> None:
    """On pass, the summary field from the report is printed to stdout."""
    from atdd.coach.commands import judge as judge_mod
    from atdd.coach.commands.coach_review import run_review

    report = _report("pass")
    report["summary"] = "Code looks great!"
    original_registry = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY["claude-sonnet-4-6"] = lambda: None  # type: ignore[assignment]
    try:
        with (
            patch(
                "atdd.coach.commands.coach_review._spawn_reviewer_agent",
                return_value="reviewer-pass-001",
            ),
            patch(
                "atdd.coach.commands.coach_review._wait_for_report",
                return_value=report,
            ),
            patch.dict("os.environ", {"ATDD_RUNTIME_ROOT": str(runtime_root)}),
        ):
            run_review(["--commit", "aaabbbccc1234567"])
    finally:
        judge_mod.LLM_REGISTRY.clear()
        judge_mod.LLM_REGISTRY.update(original_registry)

    captured = capsys.readouterr()
    assert "Code looks great!" in captured.out
