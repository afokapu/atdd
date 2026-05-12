# URN: test:review-phase-boundaries:review-phase-boundaries:E002-UNIT-003-output-json-flag-returns-report-payload
# Acceptance: acc:review-phase-boundaries:E002-UNIT-003-output-json-flag-returns-report-payload
# WMBT: wmbt:review-phase-boundaries:E002
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E002-UNIT-003 — `--output json` writes the validated review-report.json
payload to stdout as JSON instead of the human-readable summary.

Given:
  - A fake spawn seam with a pre-written pass report.

When:
  - run_coach_review(commit="abc1234", output="json") is called.

Then:
  - The captured output is parseable as JSON.
  - The parsed payload contains review_id, verdict, and phase from the
    original report.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_PASS_REPORT = {
    "review_id": "rev-e002-unit-003",
    "target_commit": "abc1234",
    "reviewer_agent_id": "reviewer-json-variant",
    "wmbt_urn": "wmbt:review-phase-boundaries:E002",
    "phase": "GREEN",
    "verdict": "pass",
    "tier1_risk_score": 0,
    "findings": [],
    "ac_coverage": {},
    "summary": "JSON output ok.",
    "recommendations": [],
}


class TestOutputJsonFlag:
    def test_output_json_returns_parseable_payload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import coach_review

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

        captured: list[str] = []
        monkeypatch.setattr(coach_review, "_spawn_reviewer_agent", _fake_spawn)
        monkeypatch.setattr(coach_review, "_resolve_pr_commit", lambda pr: "abc1234")
        monkeypatch.setattr(coach_review, "_print", lambda msg: captured.append(msg))

        rc = coach_review.run(commit="abc1234", output="json")

        assert rc == 0, f"expected exit 0, got {rc}"
        assert len(captured) >= 1, "expected at least one line of output"
        payload = json.loads(captured[0])
        assert payload["review_id"] == "rev-e002-unit-003"
        assert payload["verdict"] == "pass"
        assert payload["phase"] == "GREEN"
