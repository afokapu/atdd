# URN: test:author-plan-substrate:author-interlocking:E007-UNIT-002-missing-train-clean-error
# Acceptance: acc:author-plan-substrate:E007-UNIT-002-missing-train-clean-error
# WMBT: wmbt:author-plan-substrate:E007
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E007-UNIT-002 — a route whose train_path is absent raises a clean
InterlockingError and writes no partial interlocking artifact.

RED: create_interlocking does not exist yet.
"""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import create_interlocking
from atdd.planner.interlocking import InterlockingError


def _spec():
    return {
        "schema_version": "1.0.0",
        "interlocking_id": "interlocking:no-train",
        "title": "Interlocking whose route train is missing",
        "theme": "match",
        "status": "draft",
        "entrypoint": {"exposed": True, "actions": ["go"], "reason": None},
        "route_resolution": {"strategy": "fail_on_multiple_match"},
        "lifelines": [{"ref": "wagon:alpha"}, {"ref": "wagon:beta"}],
        "messages": [],
        "fragments": [
            {"id": "frag:go", "kind": "opt",
             "acceptance_refs": ["acceptance:go"],
             "guards": [{"id": "guard:go", "expression": "ready == true"}]},
        ],
        "routes": [
            {"route_id": "nominal-go", "category": "nominal",
             "priority": 10, "guard_ref": "guard:go",
             "train_id": "0001-absent-train",
             "train_path": "plan/_trains/0001-absent-train.yaml",
             "projection": {"expected_sequence_digest": "PENDING"}},
        ],
    }


def test_missing_route_train_refuses_with_no_partial_write(tmp_path):
    (tmp_path / "plan" / "_trains").mkdir(parents=True)
    with pytest.raises(InterlockingError):
        create_interlocking(_spec(), root=tmp_path)
    # No partial artifact, no registry entry.
    assert not (tmp_path / "plan" / "_trains" / "_interlockings" / "no-train.yaml").exists()
    assert not (tmp_path / "plan" / "_trains" / "_interlockings.yaml").exists()
