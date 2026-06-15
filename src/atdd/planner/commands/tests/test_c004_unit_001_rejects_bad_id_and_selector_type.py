# URN: test:author-atdd-substrate:author-scope:C004-UNIT-001-rejects-bad-id-and-selector-type
# Acceptance: acc:author-atdd-substrate:C004-UNIT-001-rejects-bad-id-and-selector-type
# WMBT: wmbt:author-atdd-substrate:C004
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C004-UNIT-001 — validate_scope rejects a bad scope_id and a bad selector type."""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_registry import validate_scope


def test_rejects_bad_scope_id():
    with pytest.raises(AuthorInputError) as exc:
        validate_scope({"scope_id": "Bad Id", "selectors": [{"type": "path_glob", "value": "x"}]})
    assert exc.value.field == "scope_id"


def test_rejects_bad_selector_type():
    with pytest.raises(AuthorInputError) as exc:
        validate_scope({"scope_id": "scope.source.python", "selectors": [{"type": "nope", "value": "x"}]})
    assert exc.value.field == "selectors"
