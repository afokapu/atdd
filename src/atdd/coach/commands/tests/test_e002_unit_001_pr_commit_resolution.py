# URN: test:review-phase-boundaries:E002-UNIT-001-pr-commit-resolution
# Acceptance: acc:review-phase-boundaries:E002-UNIT-001-pr-commit-resolution
# WMBT: wmbt:review-phase-boundaries:E002
# Phase: RED
# Layer: unit

"""E002-UNIT-001 — atdd coach review <PR-N> resolves the PR to its head commit.

When a PR number is passed, the operator trigger calls
`gh pr view <N> --json headRefOid` and uses the returned SHA as the
review target commit, without requiring --commit to be passed.
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
        "reviewer_agent_id": "reviewer-test-001",
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


def _pre_write_report(runtime_root: Path, reviewer_agent_id: str, report: dict) -> None:
    agent_dir = runtime_root / "agents" / reviewer_agent_id
    reviews_dir = agent_dir / "reviews"
    reviews_dir.mkdir(parents=True)
    (reviews_dir / f"{report['review_id']}.json").write_text(json.dumps(report))


def test_pr_number_resolved_to_commit(runtime_root: Path, tmp_path: Path) -> None:
    """PR number triggers gh pr view and the resolved SHA is used as target."""
    from atdd.coach.commands.coach_review import resolve_commit_from_pr

    expected_sha = "deadbeef1234567"
    mock_gh_output = json.dumps({"headRefOid": expected_sha})

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=mock_gh_output, stderr=""
        )
        sha = resolve_commit_from_pr(42)

    assert sha == expected_sha
    call_args = mock_run.call_args
    assert "gh" in call_args[0][0]
    assert "42" in call_args[0][0]


def test_pr_resolve_calls_headrefoid_field(runtime_root: Path) -> None:
    """gh invocation requests headRefOid JSON field."""
    from atdd.coach.commands.coach_review import resolve_commit_from_pr

    mock_gh_output = json.dumps({"headRefOid": "abc1234567890"})

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=mock_gh_output, stderr=""
        )
        sha = resolve_commit_from_pr(99)

    cmd = mock_run.call_args[0][0]
    assert "--json" in cmd
    assert "headRefOid" in " ".join(cmd)
    assert sha == "abc1234567890"


def test_run_review_with_pr_number_spawns_with_resolved_commit(
    runtime_root: Path, tmp_path: Path
) -> None:
    """run_review with a PR number resolves commit and spawns reviewer."""
    from atdd.coach.commands.coach_review import run_review

    commit_sha = "feed4321abcdef0"
    mock_gh_output = json.dumps({"headRefOid": commit_sha})

    spawned_commits: list[str] = []

    def fake_spawn_reviewer(target_commit: str, **kwargs) -> str:
        spawned_commits.append(target_commit)
        return "reviewer-test-pr-001"

    report = _pass_report(commit_sha)

    from atdd.coach.commands import judge as judge_mod
    original_registry = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY["claude-sonnet-4-6"] = lambda: None  # type: ignore[assignment]
    try:
        with (
            patch("subprocess.run") as mock_run,
            patch(
                "atdd.coach.commands.coach_review._spawn_reviewer_agent",
                side_effect=fake_spawn_reviewer,
            ),
            patch(
                "atdd.coach.commands.coach_review._wait_for_report",
                return_value=report,
            ),
            patch.dict("os.environ", {"ATDD_RUNTIME_ROOT": str(runtime_root)}),
        ):
            mock_run.return_value = MagicMock(
                returncode=0, stdout=mock_gh_output, stderr=""
            )
            rc = run_review(["42"])
    finally:
        judge_mod.LLM_REGISTRY.clear()
        judge_mod.LLM_REGISTRY.update(original_registry)

    assert rc == 0
    assert spawned_commits == [commit_sha]
