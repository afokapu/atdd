# URN: test:review-phase-boundaries:review-phase-boundaries:E002-UNIT-002-commit-variant-skips-gh-resolution
# Acceptance: acc:review-phase-boundaries:E002-UNIT-002-commit-variant-skips-gh-resolution
# WMBT: wmbt:review-phase-boundaries:E002
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E002-UNIT-002 — `--commit <sha>` uses the provided sha directly and never
calls the gh PR resolution path.

Given:
  - A fake spawn seam with a pre-written pass report.
  - The gh resolve seam is configured to raise if called.

When:
  - run_coach_review(commit="abc1234") is called.

Then:
  - The gh resolve seam is never invoked.
  - The reviewer is spawned with target_commit="abc1234".
  - The command exits 0 on a pass report.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_PASS_REPORT = {
    "review_id": "rev-e002-unit-002",
    "target_commit": "abc1234",
    "reviewer_agent_id": "reviewer-commit-variant",
    "wmbt_urn": "wmbt:review-phase-boundaries:E002",
    "phase": "GREEN",
    "verdict": "pass",
    "tier1_risk_score": 0,
    "findings": [],
    "ac_coverage": {},
    "summary": "Commit variant ok.",
    "recommendations": [],
}


class TestCommitVariantSkipsGh:
    def test_gh_resolve_never_called_when_commit_provided(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import coach_review

        runtime_root = tmp_path / ".atdd" / "runtime"
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))

        spawned_commits: list[str] = []

        def _fake_spawn(reviewer_agent_id, target_commit, runtime_root_arg, llm="claude-code"):
            agent_dir = runtime_root_arg / "agents" / reviewer_agent_id
            agent_dir.mkdir(parents=True, exist_ok=True)
            (agent_dir / "manifest.json").write_text(
                json.dumps({"agent_id": reviewer_agent_id, "persona": "reviewer"})
            )
            reviews_dir = agent_dir / "reviews"
            reviews_dir.mkdir(parents=True, exist_ok=True)
            seeded = dict(_PASS_REPORT)
            seeded["reviewer_agent_id"] = reviewer_agent_id
            seeded["target_commit"] = target_commit
            (reviews_dir / f"{seeded['review_id']}.json").write_text(json.dumps(seeded))
            spawned_commits.append(target_commit)

        def _gh_resolve_raises(pr_number: int) -> str:
            raise AssertionError(
                "_resolve_pr_commit must NOT be called when --commit is provided"
            )

        monkeypatch.setattr(coach_review, "_spawn_reviewer_agent", _fake_spawn)
        monkeypatch.setattr(coach_review, "_resolve_pr_commit", _gh_resolve_raises)
        monkeypatch.setattr(coach_review, "_print", lambda msg: None)

        rc = coach_review.run(commit="abc1234")

        assert rc == 0, f"expected exit 0 for pass verdict, got {rc}"
        assert spawned_commits == ["abc1234"], (
            f"reviewer was not spawned with the provided sha: {spawned_commits}"
        )
