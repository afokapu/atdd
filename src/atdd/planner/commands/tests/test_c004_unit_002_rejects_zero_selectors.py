# URN: test:author-atdd-substrate:author-scope:C004-UNIT-002-rejects-zero-selectors
# Acceptance: acc:author-atdd-substrate:C004-UNIT-002-rejects-zero-selectors
# WMBT: wmbt:author-atdd-substrate:C004
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C004-UNIT-002 — validate_scope rejects a scope with zero selectors."""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_registry import validate_scope


def test_rejects_zero_selectors():
    with pytest.raises(AuthorInputError) as exc:
        validate_scope({"scope_id": "scope.source.python", "selectors": []})
    assert exc.value.field == "selectors"
