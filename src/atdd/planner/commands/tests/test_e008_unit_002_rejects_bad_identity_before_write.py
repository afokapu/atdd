# URN: test:author-plan-substrate:author-contract:E008-UNIT-002-rejects-bad-identity-before-write
# Acceptance: acc:author-plan-substrate:E008-UNIT-002-rejects-bad-identity-before-write
# WMBT: wmbt:author-plan-substrate:E008
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E008-UNIT-002 (plan contract) — an identity of the wrong shape or an unknown
theme is rejected with the offending field BEFORE any file is written.

RED until create_contract / validate_contract exist (#1314 B).
"""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError, create_contract


def _contracts_untouched(root) -> bool:
    return not (root / "contracts").exists()


@pytest.mark.parametrize(
    "spec, field",
    [
        # malformed identity — only a theme, no aspect segment
        ({"identity": "commons", "title": "X"}, "identity"),
        # malformed identity — uppercase / illegal chars
        ({"identity": "Commons:Compliance:Probe", "title": "X"}, "identity"),
        # unknown theme (not in get_theme_map) — the classic round:result mistake
        ({"identity": "round:result", "title": "X"}, "theme"),
        # missing title
        ({"identity": "commons:compliance:probe"}, "title"),
    ],
)
def test_create_contract_rejects_before_any_write(tmp_path, spec, field):
    with pytest.raises(AuthorInputError) as exc:
        create_contract(spec, root=tmp_path)
    assert exc.value.field == field
    # No partial write: not the schema file, not the registry.
    assert _contracts_untouched(tmp_path)
