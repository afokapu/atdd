# URN: test:review-phase-boundaries:review-phase-boundaries:E002-INTEGRATION-001-cli-dispatch-routes-review
# Acceptance: acc:review-phase-boundaries:E002-UNIT-001-coach-review-pr-spawns-reviewer-and-exits-on-verdict
# WMBT: wmbt:review-phase-boundaries:E002
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E002-INTEGRATION-001 — `atdd coach review` is reachable via the top-level
CLI dispatch and does not break existing `atdd coach <N>` invocations.

Verifies that `run_cli(['review', '--commit', 'abc1234'])` routes to the
coach_review module (not the state-machine path).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


_PASS_REPORT = {
    "review_id": "rev-e002-integration-001",
    "target_commit": "abc1234",
    "reviewer_agent_id": "reviewer-integration-001",
    "wmbt_urn": "wmbt:review-phase-boundaries:E002",
    "phase": "GREEN",
    "verdict": "pass",
    "tier1_risk_score": 0,
    "findings": [],
    "ac_coverage": {},
    "summary": "Integration routing ok.",
    "recommendations": [],
}


class TestCliDispatchRoutesReview:
    def test_run_cli_routes_review_subcommand(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import coach, coach_review

        runtime_root = tmp_path / ".atdd" / "runtime"
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))

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
            (reviews_dir / f"{seeded['review_id']}.json").write_text(json.dumps(seeded))

        monkeypatch.setattr(coach_review, "_spawn_reviewer_agent", _fake_spawn)
        monkeypatch.setattr(coach_review, "_resolve_pr_commit", lambda pr: "abc1234")
        monkeypatch.setattr(coach_review, "_print", lambda msg: None)

        rc = coach.run_cli(["review", "--commit", "abc1234"])

        assert rc == 0, f"expected run_cli(['review', '--commit', 'abc1234']) → 0, got {rc}"

    def test_existing_coach_number_invocation_not_broken(
        self, tmp_path: Path
    ):
        from atdd.coach.commands import coach

        # --dry-run keeps this routing-only test hermetic: the coach CLI gates
        # every multiplexer spawn behind `if not cfg.dry_run`, so a bare issue
        # number still routes to the coach state-machine path (run_cli → 0)
        # without spawning — and leaking — a real ATDD358 cmux workspace.
        result_code = coach.run_cli(["358", "--dry-run"])
        assert result_code == 0, (
            f"atdd coach 358 regressed after adding review subcommand, got {result_code}"
        )
