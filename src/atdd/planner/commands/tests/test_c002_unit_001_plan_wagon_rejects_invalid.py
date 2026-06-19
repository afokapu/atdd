# URN: test:author-plan-substrate:author-wagon:C002-UNIT-001-rejects-missing-field-and-produce-keys
# Acceptance: acc:author-plan-substrate:C002-UNIT-001-rejects-missing-header-field
# WMBT: wmbt:author-plan-substrate:C002
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C002-UNIT-001 (plan wagon) — create_wagon rejects a structurally invalid manifest, writing nothing.

RED: create_wagon / validate_wagon do not exist yet.
"""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError, create_wagon


def test_create_wagon_rejects_missing_required_field(tmp_path):
    spec = {
        "wagon": "demo-wagon",
        "description": "missing the goal field on purpose",
        "subject": "agent:planner",
        "context": "authoring-demo",
        "action": "writes a manifest",
        # "goal" intentionally omitted
        "outcome": "n/a",
        "produce": [{"name": "commons:demo:thing"}],
    }
    with pytest.raises(AuthorInputError):
        create_wagon(spec, root=tmp_path)
    assert not (tmp_path / "plan" / "demo_wagon" / "_demo_wagon.yaml").exists()
