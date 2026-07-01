"""Shared fixtures for the convention-graph validator conformance tests (#1204).

These tests are RED until #1204 GREEN creates the
``src/atdd/validators/conventions/`` family/template architecture.
"""
from __future__ import annotations

from pathlib import Path

import pytest

# Canonical catalogue from issue #1204 (source of truth for the RED contract).
CANONICAL_FAMILIES = [
    "presence",
    "uniqueness",
    "resolution",
    "schema",
    "grammar",
    "composition",
    "coverage",
    "sizing",
    "coherence",
    "acyclicity",
    "boundary",
    "policy",
    "binding",
]

CANONICAL_TEMPLATES = {
    "presence": [
        "required_field_presence",
        "required_relationship_presence",
        "conditional_requirement",
    ],
    "uniqueness": ["scoped_identifier_uniqueness", "duplicate_edge_absence"],
    "resolution": [
        "direct_reference_resolution",
        "artifact_reference_resolution",
        "reference_chain_resolution",
    ],
    "schema": ["node_schema_conformance", "required_field_presence"],
    "grammar": ["identifier_grammar_conformance"],
    "composition": [
        "composed_graph_loads",
        "composition_merge_identity",
        "post_composition_edge_legality",
    ],
    "coverage": [
        "reachability_no_orphan",
        "source_has_required_target",
        "projection_covers_source",
    ],
    "sizing": ["cardinality_bounds"],
    "coherence": ["resolved_fact_agreement"],
    "acyclicity": ["forbidden_cycle_absence"],
    "boundary": ["allowed_boundary_crossing"],
    "policy": ["forbidden_construct_absence"],
    "binding": [
        "declaration_to_implementation_binding",
        "emitted_identity_roundtrip",
    ],
}

# Mandatory template-contract metadata fields (#1204 "Required template contract").
MANDATORY_TEMPLATE_FIELDS = [
    "family_id",
    "template_id",
    "question",
    "selector",
    "traversal",
    "invariant",
    "auto_capture",
    "failure_evidence",
]


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


@pytest.fixture
def canonical_families() -> list:
    return list(CANONICAL_FAMILIES)


@pytest.fixture
def canonical_templates() -> dict:
    return dict(CANONICAL_TEMPLATES)


@pytest.fixture
def mandatory_template_fields() -> list:
    return list(MANDATORY_TEMPLATE_FIELDS)


@pytest.fixture
def repo_root() -> Path:
    return _repo_root()


@pytest.fixture
def conventions_dir(repo_root: Path) -> Path:
    return repo_root / "src" / "atdd" / "validators" / "conventions"
