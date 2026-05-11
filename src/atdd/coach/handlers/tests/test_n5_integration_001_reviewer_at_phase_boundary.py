# URN: test:integration-hardening:N5-INTEGRATION-001-reviewer-at-phase-boundary
# Acceptance: acc:integration-hardening:N5-INTEGRATION-001-reviewer-at-phase-boundary
# Phase: RED
# Layer: unit
"""N5-INTEGRATION-001 — reviewer agent spawns at each enabled phase boundary.

Per spec §6.3: when `--review-phases` includes a phase, a reviewer persona
is spawned at that phase boundary and its manifest is written to
`.atdd/runtime/agents/<reviewer-id>/`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

pytestmark = [pytest.mark.platform]


def _pass_report(phase: str = "GREEN") -> dict:
    # Schema (review-report.schema.json) only permits RED/GREEN/SMOKE/REFACTOR.
    valid_phase = phase if phase in ("RED", "GREEN", "SMOKE", "REFACTOR") else "GREEN"
    return {
        "review_id": f"rev-pass-{phase.lower()}",
        "target_commit": "deadbeef00",
        "reviewer_agent_id": "reviewer-test-001",
        "wmbt_urn": "wmbt:integration-hardening:N5",
        "phase": valid_phase,
        "verdict": "pass",
        "tier1_risk_score": 0,
        "findings": [],
        "ac_coverage": {},
        "summary": "All good.",
        "recommendations": [],
    }


@pytest.fixture()
def runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / ".atdd" / "runtime"
    root.mkdir(parents=True)
    return root


def _make_ctx(
    review_phases: set,
    skip_review: bool = False,
    dry_run: bool = False,
    issue_number: int = 589,
):
    from atdd.coach.handlers.state_machine import CoachContext

    return CoachContext(
        issue_number=issue_number,
        review_phases=review_phases,
        skip_review=skip_review,
        dry_run=dry_run,
    )


def _fake_spawn(ctx, transition, reviewer_agent_id, runtime_root_path):
    """No-op spawn: does not start a real process."""


def _fake_wait(reviewer_agent_dir: Path, **kwargs) -> Optional[dict]:
    """Immediately return a pass report without polling."""
    return _pass_report("GREEN")


ALL_REVIEW_PHASES = {"planned", "red", "green", "smoke", "refactor"}


class TestReviewerSpawnedAtEachPhase:
    """Reviewer manifest is written for each enabled phase boundary."""

    @pytest.mark.parametrize("phase_name", ["planned", "red", "green", "smoke", "refactor"])
    def test_reviewer_manifest_written_for_each_phase(
        self,
        runtime_root: Path,
        monkeypatch: pytest.MonkeyPatch,
        phase_name: str,
    ):
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))

        from atdd.coach.handlers import reviewer as rev_handler
        monkeypatch.setattr(rev_handler, "_spawn_reviewer", _fake_spawn)
        monkeypatch.setattr(rev_handler, "_wait_for_review_report", _fake_wait)

        from atdd.coach.handlers.state_machine import HandlerResult, Phase, Transition

        phase_enum = Phase(phase_name.upper())
        ctx = _make_ctx(review_phases=ALL_REVIEW_PHASES)
        transition = Transition(src=Phase.INIT, dst=phase_enum)

        result = rev_handler.handle(ctx, transition)

        assert result == HandlerResult.HANDLED

        agents_dir = runtime_root / "agents"
        reviewer_manifests = []
        for agent_dir in agents_dir.iterdir():
            m = agent_dir / "manifest.json"
            if m.is_file():
                data = json.loads(m.read_text())
                if data.get("persona") == "reviewer":
                    reviewer_manifests.append(data)

        assert len(reviewer_manifests) == 1, (
            f"Expected exactly one reviewer manifest for phase {phase_name}, "
            f"got {len(reviewer_manifests)}"
        )
        assert reviewer_manifests[0]["phase"] == phase_name.upper()
        assert reviewer_manifests[0]["issue"] == 589

    def test_reviewer_not_spawned_when_phase_not_in_review_phases(
        self,
        runtime_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))

        from atdd.coach.handlers import reviewer as rev_handler
        monkeypatch.setattr(rev_handler, "_spawn_reviewer", _fake_spawn)
        monkeypatch.setattr(rev_handler, "_wait_for_review_report", _fake_wait)

        from atdd.coach.handlers.state_machine import HandlerResult, Phase, Transition

        ctx = _make_ctx(review_phases={"red", "green"})  # PLANNED not included
        transition = Transition(src=Phase.INIT, dst=Phase.PLANNED)

        result = rev_handler.handle(ctx, transition)

        assert result == HandlerResult.NOOP
        agents_dir = runtime_root / "agents"
        reviewer_manifests = []
        if agents_dir.exists():
            for agent_dir in agents_dir.iterdir():
                m = agent_dir / "manifest.json"
                if m.is_file():
                    data = json.loads(m.read_text())
                    if data.get("persona") == "reviewer":
                        reviewer_manifests.append(data)
        assert len(reviewer_manifests) == 0
