# URN: test:review-phase-boundaries:phase-boundary-review:E005-UNIT-002-skip-review-bypasses-default
# Acceptance: acc:review-phase-boundaries:E005-UNIT-002-skip-review-bypasses-default
# WMBT: wmbt:review-phase-boundaries:E005
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: parse_cli with --skip-review sets skip_review=True regardless of default review_phases
"""RED Test for E005-UNIT-002 — --skip-review bypasses the default refactor review.

`--skip-review` is the explicit opt-out: the operator passes it to disable
review at all phase boundaries including the default refactor boundary.
"""
from __future__ import annotations

import pytest


class TestSkipReviewBypassesDefault:
    """--skip-review sets skip_review=True; reviewer handler then returns NOOP."""

    def test_skip_review_flag_sets_skip_review_true(self) -> None:
        from atdd.coach.commands.coach import parse_cli

        cfg = parse_cli(["999", "--skip-review"])

        assert cfg.skip_review is True, (
            f"Expected skip_review == True, got {cfg.skip_review!r}."
        )

    def test_skip_review_reviewer_handler_returns_noop_at_refactor(self) -> None:
        """With skip_review=True, the reviewer handler returns NOOP even at REFACTOR."""
        from atdd.coach.commands.coach import parse_cli
        from atdd.coach.handlers import reviewer as rev_handler
        from atdd.coach.handlers.state_machine import (
            CoachContext,
            HandlerResult,
            Phase,
            Transition,
        )

        cfg = parse_cli(["999", "--skip-review"])
        ctx = CoachContext(
            issue_number=999,
            review_phases=cfg.review_phases,
            skip_review=cfg.skip_review,
        )
        transition = Transition(src=Phase.SMOKE, dst=Phase.REFACTOR)

        result = rev_handler.handle(ctx, transition)

        assert result == HandlerResult.NOOP, (
            f"Expected NOOP when skip_review=True, got {result!r}."
        )
