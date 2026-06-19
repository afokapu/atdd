# URN: test:author-plan-substrate:author-acceptance:C006-UNIT-001-rejects-missing-target-and-bad-phase
# Acceptance: acc:author-plan-substrate:C006-UNIT-001-rejects-missing-target-and-bad-phase
# WMBT: wmbt:author-plan-substrate:C006
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C006-UNIT-001 (plan acceptance) — create_acceptance rejects a missing target WMBT.

RED: create_acceptance / validate_acceptance do not exist yet.
"""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError, create_acceptance


def test_create_acceptance_rejects_missing_target(tmp_path):
    (tmp_path / "plan").mkdir()
    block = {
        "identity": {"urn": "acc:demo-wagon:E001-UNIT-001-x", "id": "AC-UNIT-001",
                     "purpose": "x", "phase": "GREEN"},
        "harness": {"type": "unit", "category": "backend"},
        "given": {"abstract": ["a"]},
        "when": {"abstract": "b"},
        "then": {"abstract": ["c"]},
    }
    with pytest.raises(AuthorInputError):
        create_acceptance("wmbt:demo-wagon:NOPE", block, root=tmp_path)
