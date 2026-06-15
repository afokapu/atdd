# URN: test:author-atdd-substrate:substrate-spine:C001-UNIT-001-spine-rejects-bad-role
# Acceptance: acc:author-atdd-substrate:C001-UNIT-001-spine-rejects-bad-role
# WMBT: wmbt:author-atdd-substrate:C001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C001-UNIT-001 — the `atdd author` spine rejects an unknown role before dispatch.

Given an author input whose role is not a known ATDD role, the shared
validation spine must fail with a role error and never reach a per-kind
writer.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.planner.commands.author import AuthorInputError, validate_author_input


def test_spine_rejects_unknown_role():
    with pytest.raises(AuthorInputError) as exc:
        validate_author_input(
            role="nonsense",
            rule_id="nonsense.green.component-urn-marker-is",
            path=Path("src/atdd/nonsense/conventions/nodes/x.convention.yaml"),
        )
    assert exc.value.field == "role"
    assert "role" in str(exc.value).lower()
