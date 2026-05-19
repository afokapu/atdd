# URN: test:review-phase-boundaries:phase-boundary-review:E005-UNIT-003-explicit-review-phases-override
# Acceptance: acc:review-phase-boundaries:E005-UNIT-003-explicit-review-phases-override
# WMBT: wmbt:review-phase-boundaries:E005
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: parse_cli with --review-phases green,smoke overrides the default and uses exactly that set
"""RED Test for E005-UNIT-003 — explicit --review-phases overrides the default.

When `--review-phases` is provided explicitly, it replaces the default {"refactor"}
entirely. The operator can choose any combination of phases.
"""
from __future__ import annotations

import pytest


class TestExplicitReviewPhasesOverride:
    """--review-phases <phases> replaces the {"refactor"} default with the given set."""

    def test_explicit_review_phases_replaces_default(self) -> None:
        from atdd.coach.commands.coach import parse_cli

        cfg = parse_cli(["999", "--review-phases", "green,smoke"])

        assert cfg.review_phases == {"green", "smoke"}, (
            f"Expected review_phases == {{'green', 'smoke'}}, got {cfg.review_phases!r}. "
            "An explicit --review-phases must replace (not augment) the default."
        )

    def test_explicit_review_phases_does_not_include_refactor_by_default(self) -> None:
        """refactor must not leak into an explicit override that excludes it."""
        from atdd.coach.commands.coach import parse_cli

        cfg = parse_cli(["999", "--review-phases", "green"])

        assert "refactor" not in cfg.review_phases, (
            f"'refactor' must not appear when only 'green' was requested; "
            f"got {cfg.review_phases!r}."
        )

    def test_explicit_refactor_in_review_phases_is_accepted(self) -> None:
        from atdd.coach.commands.coach import parse_cli

        cfg = parse_cli(["999", "--review-phases", "refactor,green"])

        assert cfg.review_phases == {"refactor", "green"}, (
            f"Expected {{'refactor', 'green'}}, got {cfg.review_phases!r}."
        )

    def test_empty_review_phases_string_produces_empty_set(self) -> None:
        """--review-phases '' (empty string) explicitly opts out of all reviews."""
        from atdd.coach.commands.coach import parse_cli

        cfg = parse_cli(["999", "--review-phases", ""])

        assert cfg.review_phases == set(), (
            f"Expected empty set, got {cfg.review_phases!r}. "
            "An empty --review-phases value must produce an empty set."
        )
