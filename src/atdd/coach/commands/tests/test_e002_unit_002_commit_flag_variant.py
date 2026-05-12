# URN: test:review-phase-boundaries:E002-UNIT-002-commit-flag-variant
# Acceptance: acc:review-phase-boundaries:E002-UNIT-002-commit-flag-variant
# WMBT: wmbt:review-phase-boundaries:E002
# Phase: RED
# Layer: unit

"""E002-UNIT-002 — atdd coach review --commit <sha> bypasses gh entirely.

When --commit <sha> is provided, no gh subprocess call is made and the
SHA is used directly as the review target. Exits 0 on pass verdict.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.platform]


def _pass_report(commit_sha: str) -> dict:
    return {
        "review_id": str(uuid.uuid4()),
        "target_commit": commit_sha,
        "reviewer_agent_id": "reviewer-test-002",
        "wmbt_urn": "wmbt:review-phase-boundaries:E002",
        "phase": "GREEN",
        "verdict": "pass",
        "tier1_risk_score": 0,
        "findings": [],
        "ac_coverage": {},
        "summary": "All checks passed.",
    }


@pytest.fixture()
def runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / ".atdd" / "runtime"
    root.mkdir(parents=True)
    return root


def test_commit_flag_skips_gh_invocation(runtime_root: Path) -> None:
    """--commit <sha> does not invoke gh."""
    from atdd.coach.commands.coach_review import run_review

    commit_sha = "cafebabe12345678"
    report = _pass_report(commit_sha)
    spawned_commits: list[str] = []

    def fake_spawn(target_commit: str, **kwargs) -> str:
        spawned_commits.append(target_commit)
        return "reviewer-commit-001"

    from atdd.coach.commands import judge as judge_mod
    original_registry = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY["claude-sonnet-4-6"] = lambda: None  # type: ignore[assignment]
    try:
        with (
            patch("subprocess.run") as mock_run,
            patch(
                "atdd.coach.commands.coach_review._spawn_reviewer_agent",
                side_effect=fake_spawn,
            ),
            patch(
                "atdd.coach.commands.coach_review._wait_for_report",
                return_value=report,
            ),
            patch.dict("os.environ", {"ATDD_RUNTIME_ROOT": str(runtime_root)}),
        ):
            rc = run_review(["--commit", commit_sha])
    finally:
        judge_mod.LLM_REGISTRY.clear()
        judge_mod.LLM_REGISTRY.update(original_registry)

    assert rc == 0
    assert spawned_commits == [commit_sha]
    # gh should NOT have been called
    for call in mock_run.call_args_list:
        cmd = call[0][0] if call[0] else []
        assert "gh" not in str(cmd), f"gh was called unexpectedly: {cmd}"


def test_commit_flag_passed_directly_to_spawn(runtime_root: Path) -> None:
    """The exact SHA from --commit is forwarded to the reviewer spawn."""
    from atdd.coach.commands.coach_review import run_review

    commit_sha = "0123456789abcdef"
    report = _pass_report(commit_sha)
    received: dict = {}

    def capture_spawn(target_commit: str, **kwargs) -> str:
        received["target_commit"] = target_commit
        return "reviewer-capture-001"

    from atdd.coach.commands import judge as judge_mod
    original_registry = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY["claude-sonnet-4-6"] = lambda: None  # type: ignore[assignment]
    try:
        with (
            patch("subprocess.run"),
            patch(
                "atdd.coach.commands.coach_review._spawn_reviewer_agent",
                side_effect=capture_spawn,
            ),
            patch(
                "atdd.coach.commands.coach_review._wait_for_report",
                return_value=report,
            ),
            patch.dict("os.environ", {"ATDD_RUNTIME_ROOT": str(runtime_root)}),
        ):
            run_review(["--commit", commit_sha])
    finally:
        judge_mod.LLM_REGISTRY.clear()
        judge_mod.LLM_REGISTRY.update(original_registry)

    assert received["target_commit"] == commit_sha
