# URN: test:author-plan-substrate:author-plan-spine:C001-UNIT-001-guard-rejects-bad-slug-and-path
# Acceptance: acc:author-plan-substrate:C001-UNIT-001-guard-rejects-bad-slug-and-path
# WMBT: wmbt:author-plan-substrate:C001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C001-UNIT-001 (plan spine) — the plan-artifact guard rejects a bad slug / out-of-plan path.

RED: validate_plan_author_input does not exist yet on the author spine.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.planner.commands.author import AuthorInputError, validate_plan_author_input


def test_guard_rejects_non_kebab_slug(tmp_path):
    with pytest.raises(AuthorInputError) as ei:
        validate_plan_author_input(
            "Not_Kebab", "wagon:not-kebab", tmp_path / "plan" / "x" / "_x.yaml",
            plan_root=str(tmp_path / "plan"),
        )
    assert ei.value.field == "slug"


def test_guard_rejects_path_outside_plan(tmp_path):
    with pytest.raises(AuthorInputError) as ei:
        validate_plan_author_input(
            "ok-slug", "wagon:ok-slug", tmp_path / "src" / "escape.yaml",
            plan_root=str(tmp_path / "plan"),
        )
    assert ei.value.field == "path"
