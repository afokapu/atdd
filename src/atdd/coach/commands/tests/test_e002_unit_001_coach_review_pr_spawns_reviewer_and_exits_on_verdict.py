# URN: test:review-phase-boundaries:review-phase-boundaries:E002-UNIT-001-coach-review-pr-spawns-reviewer-and-exits-on-verdict
# Acceptance: acc:review-phase-boundaries:E002-UNIT-001-coach-review-pr-spawns-reviewer-and-exits-on-verdict
# WMBT: wmbt:review-phase-boundaries:E002
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E002-UNIT-001 — `atdd coach review <N>` spawns a reviewer-persona agent,
waits for review-report.json, prints the verdict to stdout, and exits 0 on
pass or nonzero on fail.

Given:
  - A fake spawn seam that writes a reviewer manifest and pre-populates
    reviews/<review-id>.json with a conforming pass (or fail) report.
  - A fake gh-resolve seam that returns a fixed sha.

When:
  - The operator calls run_coach_review(pr_number=100, ...) or
    run_coach_review(pr_number=100) for the fail variant.

Then:
  - A reviewer-persona manifest.json is present at
    .atdd/runtime/agents/<reviewer-id>/manifest.json with persona=reviewer.
  - stdout contains the verdict.
  - exit code is 0 for pass, nonzero for fail.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

pytestmark = [pytest.mark.platform]

_PASS_REPORT = {
    "review_id": "rev-e002-unit-001",
    "target_commit": "deadbeef01",
    "reviewer_agent_id": "reviewer-100-green-abcdef01",
    "wmbt_urn": "wmbt:review-phase-boundaries:E002",
    "phase": "GREEN",
    "verdict": "pass",
    "tier1_risk_score": 0,
    "findings": [],
    "ac_coverage": {},
    "summary": "All acceptances covered.",
    "recommendations": [],
}

_FAIL_REPORT = {
    **_PASS_REPORT,
    "review_id": "rev-e002-unit-001-fail",
    "verdict": "fail",
    "summary": "Strict finding present.",
}


def _make_fake_spawn(report: dict, runtime_root: Path):
    """Return a fake spawn callable that writes manifest + pre-seeds the report."""

    def _fake_spawn(
        reviewer_agent_id: str,
        target_commit: str,
        runtime_root_arg: Path,
        llm: str = "claude-code",
    ) -> None:
        agent_dir = runtime_root_arg / "agents" / reviewer_agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "agent_id": reviewer_agent_id,
            "persona": "reviewer",
            "issue": None,
            "phase": "GREEN",
        }
        (agent_dir / "manifest.json").write_text(json.dumps(manifest))
        reviews_dir = agent_dir / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        seeded = dict(report)
        seeded["reviewer_agent_id"] = reviewer_agent_id
        (reviews_dir / f"{seeded['review_id']}.json").write_text(
            json.dumps(seeded)
        )

    return _fake_spawn


def _fake_resolve_pr(pr_number: int) -> str:
    return "deadbeef01"


class TestCoachReviewPassVerdict:
    def test_exits_zero_and_prints_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import coach_review

        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(tmp_path / ".atdd" / "runtime"))
        monkeypatch.setattr(coach_review, "_spawn_reviewer_agent", _make_fake_spawn(
            _PASS_REPORT, tmp_path / ".atdd" / "runtime"
        ))
        monkeypatch.setattr(coach_review, "_resolve_pr_commit", _fake_resolve_pr)

        captured: list[str] = []
        monkeypatch.setattr(coach_review, "_print", lambda msg: captured.append(msg))

        rc = coach_review.run(pr_number=100)

        assert rc == 0, f"expected exit 0 for pass verdict, got {rc}"
        assert any("pass" in line.lower() for line in captured), (
            f"expected 'pass' in output, got: {captured}"
        )

    def test_reviewer_manifest_written_with_persona_reviewer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import coach_review

        runtime_root = tmp_path / ".atdd" / "runtime"
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))
        monkeypatch.setattr(
            coach_review, "_spawn_reviewer_agent",
            _make_fake_spawn(_PASS_REPORT, runtime_root),
        )
        monkeypatch.setattr(coach_review, "_resolve_pr_commit", _fake_resolve_pr)
        monkeypatch.setattr(coach_review, "_print", lambda msg: None)

        coach_review.run(pr_number=100)

        agents_dir = runtime_root / "agents"
        reviewer_dirs = list(agents_dir.iterdir()) if agents_dir.exists() else []
        assert len(reviewer_dirs) == 1, (
            f"expected exactly one reviewer agent dir, got: {reviewer_dirs}"
        )
        manifest_path = reviewer_dirs[0] / "manifest.json"
        assert manifest_path.is_file(), "manifest.json not written"
        manifest = json.loads(manifest_path.read_text())
        assert manifest.get("persona") == "reviewer", (
            f"expected persona=reviewer, got {manifest.get('persona')!r}"
        )


class TestCoachReviewFailVerdict:
    def test_exits_nonzero_on_fail(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import coach_review

        runtime_root = tmp_path / ".atdd" / "runtime"
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))
        monkeypatch.setattr(
            coach_review, "_spawn_reviewer_agent",
            _make_fake_spawn(_FAIL_REPORT, runtime_root),
        )
        monkeypatch.setattr(coach_review, "_resolve_pr_commit", _fake_resolve_pr)
        monkeypatch.setattr(coach_review, "_print", lambda msg: None)
        monkeypatch.setattr(coach_review, "_print_err", lambda msg: None)

        rc = coach_review.run(pr_number=100)

        assert rc != 0, "expected nonzero exit for fail verdict"
