# URN: test:review-phase-boundaries:phase-boundary-review:E005-UNIT-001-parse-cli-defaults-review-phases-to-refactor
# Acceptance: acc:review-phase-boundaries:E005-UNIT-001-parse-cli-defaults-review-phases-to-refactor
# WMBT: wmbt:review-phase-boundaries:E005
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: parse_cli with no --review-phases flag produces review_phases == {"refactor"}
"""RED Test for E005-UNIT-001 — parse_cli defaults review_phases to {"refactor"}.

When an operator runs a plain `atdd coach <N>` with no --review-phases flag,
the resulting Config must have review_phases == {"refactor"} so that a reviewer
is spawned at the pre-COMPLETE boundary automatically.
"""
from __future__ import annotations

import pytest


class TestParseCLIDefaultsReviewPhasesToRefactor:
    """parse_cli without --review-phases uses {"refactor"} as the default."""

    def test_bare_issue_number_review_phases_defaults_to_refactor(self) -> None:
        from atdd.coach.commands.coach import parse_cli

        cfg = parse_cli(["999"])

        assert cfg.review_phases == {"refactor"}, (
            f"Expected review_phases == {{'refactor'}}, got {cfg.review_phases!r}. "
            "A plain `atdd coach <N>` must default to reviewing at the pre-COMPLETE "
            "boundary without requiring --review-phases."
        )

    def test_default_skip_review_is_false(self) -> None:
        from atdd.coach.commands.coach import parse_cli

        cfg = parse_cli(["999"])

        assert cfg.skip_review is False, (
            f"Expected skip_review == False, got {cfg.skip_review!r}."
        )

    def test_multiple_issue_numbers_still_default_to_refactor(self) -> None:
        from atdd.coach.commands.coach import parse_cli

        cfg = parse_cli(["100", "200", "300"])

        assert cfg.review_phases == {"refactor"}, (
            f"Expected review_phases == {{'refactor'}}, got {cfg.review_phases!r}."
        )
