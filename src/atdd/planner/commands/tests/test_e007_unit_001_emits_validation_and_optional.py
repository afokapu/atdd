# URN: test:author-atdd-substrate:author-convention-node:E007-UNIT-001-emits-validation-and-stays-optional
# Acceptance: acc:author-atdd-substrate:E007-UNIT-001-emits-validation-and-stays-optional
# WMBT: wmbt:author-atdd-substrate:E007
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E007-UNIT-001 — create_convention_node emits an optional top-level `validation`
block (and nodes authored without it stay schema-valid)."""
from __future__ import annotations

import yaml

from atdd.planner.commands.author import (
    create_convention_node,
    validate_convention_node,
)

_TERMS = [{"term_id": "interlocking", "text": "the route-control model for the train domain"}]


def _validation(subject_kind: str = "interlocking") -> dict:
    return {
        "family": "coherence",
        "template": "resolved_fact_agreement",
        "variant": "planner_train_interlocking_projection_equivalence",
        "phase": "GREEN",
        "enforcement": "strict",
        "subject_kind": subject_kind,
        "selector": "rules tagged subject_kind=interlocking",
        "traversal": "interlocking-node -> projected-diagram",
        "invariant": "projection equals declared route table",
        "failure_evidence": ["interlocking_node_id", "diverging_field"],
        "config": {"projection": "route-table"},
    }


def test_create_emits_top_level_validation(tmp_path):
    path = create_convention_node(
        "planner",
        "planner.train.interlocking-projection-equivalence",
        statement="An interlocking projection must equal its declared route table.",
        terms=_TERMS,
        validation=_validation(),
        root=tmp_path,
    )
    node = yaml.safe_load(path.read_text())
    assert node["validation"] == _validation()
    # the artifact validates against the canonical convention-node schema
    validate_convention_node(node, path)


def test_node_without_validation_stays_valid(tmp_path):
    path = create_convention_node(
        "planner",
        "planner.train.interlocking-home",
        statement="Interlocking conventions live in the planner train family.",
        terms=_TERMS,
        root=tmp_path,
    )
    node = yaml.safe_load(path.read_text())
    assert "validation" not in node
    validate_convention_node(node, path)


def test_subject_kind_interlocking_and_runtime_boundary_accepted(tmp_path):
    for i, kind in enumerate(("interlocking", "runtime-boundary")):
        path = create_convention_node(
            "planner",
            f"planner.train.interlocking-subject-{i}",
            statement=f"Subject kind {kind} is accepted by the validation metadata.",
            terms=_TERMS,
            validation=_validation(subject_kind=kind),
            root=tmp_path,
        )
        node = yaml.safe_load(path.read_text())
        assert node["validation"]["subject_kind"] == kind
        validate_convention_node(node, path)
