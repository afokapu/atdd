# URN: test:review-phase-boundaries:phase-boundary-review:E005-INTEGRATION-001-reviewer-fires-at-refactor-boundary-by-default
# Acceptance: acc:review-phase-boundaries:E005-INTEGRATION-001-reviewer-fires-at-refactor-boundary-by-default
# WMBT: wmbt:review-phase-boundaries:E005
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: With the default review_phases={"refactor"}, reviewer.handle() returns HANDLED when entering REFACTOR (the pre-COMPLETE boundary)
"""RED Test for E005-INTEGRATION-001 — reviewer fires at REFACTOR entry (pre-COMPLETE boundary) with default config.

When review_phases is the new default {"refactor"} and skip_review is False,
the reviewer handler must return HANDLED at the SMOKE→REFACTOR transition
(entering REFACTOR, the last phase before COMPLETE), proving that a plain
`atdd coach <N>` triggers a review before COMPLETE.

The reviewer handler checks transition.dst.value.lower() against review_phases,
so "refactor" in review_phases fires when dst=Phase.REFACTOR (SMOKE→REFACTOR).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

pytestmark = [pytest.mark.platform]


def _pass_report() -> dict:
    return {
        "review_id": "rev-e005-pass",
        "target_commit": "deadbeef00",
        "reviewer_agent_id": "reviewer-test-e005",
        "wmbt_urn": "wmbt:review-phase-boundaries:E005",
        "phase": "REFACTOR",
        "verdict": "pass",
        "tier1_risk_score": 0,
        "findings": [],
        "ac_coverage": {},
        "summary": "Default review at pre-COMPLETE boundary passes.",
        "recommendations": [],
    }


def _fake_spawn(ctx, transition, reviewer_agent_id, runtime_root_path) -> None:
    """No-op spawn: does not start a real process."""


def _fake_wait(reviewer_agent_dir: Path, **kwargs) -> Optional[dict]:
    """Immediately return a pass report without polling."""
    return _pass_report()


@pytest.fixture()
def runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / ".atdd" / "runtime"
    root.mkdir(parents=True)
    return root


class TestReviewerFiresAtRefactorBoundaryByDefault:
    """With the default review_phases={"refactor"}, reviewer handle() fires at SMOKE→REFACTOR."""

    def test_default_review_phases_triggers_handled_at_smoke_to_refactor(
        self,
        runtime_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The SMOKE→REFACTOR transition is the pre-COMPLETE boundary; default review_phases={"refactor"} fires here."""
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))

        from atdd.coach.handlers import reviewer as rev_handler
        monkeypatch.setattr(rev_handler, "_spawn_reviewer", _fake_spawn)
        monkeypatch.setattr(rev_handler, "_wait_for_review_report", _fake_wait)

        from atdd.coach.handlers.state_machine import (
            CoachContext,
            HandlerResult,
            Phase,
            Transition,
        )

        # Use the default review_phases value from parse_cli ({"refactor"})
        ctx = CoachContext(
            issue_number=722,
            review_phases={"refactor"},
            skip_review=False,
        )
        # SMOKE→REFACTOR: dst.value.lower() == "refactor" which IS in review_phases
        transition = Transition(src=Phase.SMOKE, dst=Phase.REFACTOR)

        result = rev_handler.handle(ctx, transition)

        assert result == HandlerResult.HANDLED, (
            f"Expected HANDLED at SMOKE→REFACTOR with default review_phases={{'refactor'}}, "
            f"got {result!r}."
        )

    def test_reviewer_manifest_written_at_smoke_to_refactor_with_default(
        self,
        runtime_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))

        from atdd.coach.handlers import reviewer as rev_handler
        monkeypatch.setattr(rev_handler, "_spawn_reviewer", _fake_spawn)
        monkeypatch.setattr(rev_handler, "_wait_for_review_report", _fake_wait)

        from atdd.coach.handlers.state_machine import (
            CoachContext,
            Phase,
            Transition,
        )

        ctx = CoachContext(
            issue_number=722,
            review_phases={"refactor"},
            skip_review=False,
        )
        rev_handler.handle(ctx, Transition(src=Phase.SMOKE, dst=Phase.REFACTOR))

        agents_dir = runtime_root / "agents"
        reviewer_manifests = []
        for agent_dir in agents_dir.iterdir():
            m = agent_dir / "manifest.json"
            if m.is_file():
                data = json.loads(m.read_text())
                if data.get("persona") == "reviewer":
                    reviewer_manifests.append(data)

        assert len(reviewer_manifests) == 1, (
            f"Expected exactly one reviewer manifest at SMOKE→REFACTOR, "
            f"got {len(reviewer_manifests)}."
        )
        assert reviewer_manifests[0]["phase"] == "REFACTOR", (
            f"Expected manifest phase 'REFACTOR', got {reviewer_manifests[0]['phase']!r}."
        )

    def test_noop_when_review_phases_empty_explicit(
        self,
        runtime_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Explicit empty review_phases still suppresses review (backward compat guard)."""
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))

        from atdd.coach.handlers import reviewer as rev_handler
        monkeypatch.setattr(rev_handler, "_spawn_reviewer", _fake_spawn)
        monkeypatch.setattr(rev_handler, "_wait_for_review_report", _fake_wait)

        from atdd.coach.handlers.state_machine import (
            CoachContext,
            HandlerResult,
            Phase,
            Transition,
        )

        ctx = CoachContext(
            issue_number=722,
            review_phases=set(),
            skip_review=False,
        )
        result = rev_handler.handle(ctx, Transition(src=Phase.SMOKE, dst=Phase.REFACTOR))

        assert result == HandlerResult.NOOP, (
            f"Expected NOOP with empty review_phases, got {result!r}."
        )
