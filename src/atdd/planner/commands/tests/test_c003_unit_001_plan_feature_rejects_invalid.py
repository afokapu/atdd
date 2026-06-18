# URN: test:author-plan-substrate:author-feature:C003-UNIT-001-rejects-missing-field-and-bad-wagon
# Acceptance: acc:author-plan-substrate:C003-UNIT-001-rejects-missing-field-and-bad-wagon
# WMBT: wmbt:author-plan-substrate:C003
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C003-UNIT-001 (plan feature) — create_feature rejects a malformed feature, writing nothing.

RED: create_feature does not exist yet.
"""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError, create_feature


def test_create_feature_rejects_missing_sizing(tmp_path):
    spec = {
        "urn": "feature:demo-wagon:do-thing",
        "wagon": "wagon:demo-wagon",
        "description": "missing sizing on purpose",
        # "sizing" omitted
        "wmbts": ["wmbt:demo-wagon:E001"],
        "components": {"backend": {"application": [
            {"type": "use_cases", "count": 1, "rationale": "demo"}]}},
    }
    with pytest.raises(AuthorInputError):
        create_feature(spec, root=tmp_path)
    assert not (tmp_path / "plan" / "demo_wagon" / "features" / "do_thing.yaml").exists()
