# URN: test:integration-hardening:N5-INTEGRATION-003-skip-review-honored
# Acceptance: acc:integration-hardening:N5-INTEGRATION-003-skip-review-honored
# Phase: RED
# Layer: unit
"""N5-INTEGRATION-003 — `--skip-review` bypasses all reviewer spawns.

When `ctx.skip_review` is True, the reviewer handler returns NOOP and
no reviewer manifest is written.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


@pytest.fixture()
def runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / ".atdd" / "runtime"
    root.mkdir(parents=True)
    return root


class TestSkipReviewHonored:
    """skip_review=True → NOOP at every phase boundary."""

    @pytest.mark.parametrize("phase_name", ["planned", "red", "green", "smoke", "refactor"])
    def test_skip_review_returns_noop_for_all_phases(
        self,
        runtime_root: Path,
        monkeypatch: pytest.MonkeyPatch,
        phase_name: str,
    ):
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))

        from atdd.coach.handlers import reviewer as rev_handler
        from atdd.coach.handlers.state_machine import (
            CoachContext,
            HandlerResult,
            Phase,
            Transition,
        )

        ctx = CoachContext(
            issue_number=589,
            review_phases={"planned", "red", "green", "smoke", "refactor"},
            skip_review=True,
        )
        phase_enum = Phase(phase_name.upper())
        result = rev_handler.handle(ctx, Transition(src=Phase.INIT, dst=phase_enum))

        assert result == HandlerResult.NOOP

    def test_no_reviewer_manifest_written_when_skip_review(
        self,
        runtime_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))

        from atdd.coach.handlers import reviewer as rev_handler
        from atdd.coach.handlers.state_machine import (
            CoachContext,
            HandlerResult,
            Phase,
            Transition,
        )

        ctx = CoachContext(
            issue_number=589,
            review_phases={"green"},
            skip_review=True,
        )
        rev_handler.handle(ctx, Transition(src=Phase.RED, dst=Phase.GREEN))

        agents_dir = runtime_root / "agents"
        reviewer_manifests = []
        if agents_dir.exists():
            for entry in agents_dir.iterdir():
                m = entry / "manifest.json"
                if m.is_file():
                    data = json.loads(m.read_text())
                    if data.get("persona") == "reviewer":
                        reviewer_manifests.append(data)
        assert len(reviewer_manifests) == 0, "No reviewer must be spawned when --skip-review"

    def test_empty_review_phases_returns_noop(
        self,
        runtime_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Empty review_phases set means no review at any boundary."""
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))

        from atdd.coach.handlers import reviewer as rev_handler
        from atdd.coach.handlers.state_machine import (
            CoachContext,
            HandlerResult,
            Phase,
            Transition,
        )

        ctx = CoachContext(issue_number=589, review_phases=set(), skip_review=False)
        result = rev_handler.handle(ctx, Transition(src=Phase.RED, dst=Phase.GREEN))

        assert result == HandlerResult.NOOP
