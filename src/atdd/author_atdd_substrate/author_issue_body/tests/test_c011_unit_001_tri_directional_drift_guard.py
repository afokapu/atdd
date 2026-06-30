# URN: test:author-atdd-substrate:author-issue-body:C011-UNIT-001-tri-directional-drift-guard
# Acceptance: acc:author-atdd-substrate:C011-UNIT-001-tri-directional-drift-guard
# WMBT: wmbt:author-atdd-substrate:C011
# Phase: RED
# Layer: application
"""C011-UNIT-001 — the keystone tri-directional drift-guard.

issue.schema.json's required sections == create_issue_body's emitted fields ==
the coach E019 gate's required sections (load_required_sections() +
REQUIRED_SUBSECTIONS). Removing a required section from any one surface fails the
guard, so the three surfaces can never drift apart.
"""
from __future__ import annotations

from ._helpers import (
    get_create_issue_body,
    load_issue_schema,
    required_section_set,
    sample_spec,
)


def _schema_required_sections(schema: dict) -> set[str]:
    """The required top-level section headings declared by issue.schema.json."""
    required = schema.get("required", [])
    return set(required)


def test_c011_unit_001_tri_directional_drift_guard():
    schema = load_issue_schema()
    create_issue_body = get_create_issue_body()

    schema_sections = _schema_required_sections(schema)

    # Surface 1 vs 2: schema required == E019 gate required (H2 minus optional + H3).
    gate_sections = required_section_set()
    assert schema_sections == gate_sections, (
        "schema required-sections drifted from E019 gate required-sections:\n"
        f"  only in schema: {sorted(schema_sections - gate_sections)}\n"
        f"  only in gate:   {sorted(gate_sections - schema_sections)}"
    )

    # Surface 2 vs 3: the generator emits every required section (== schema props).
    body = create_issue_body(sample_spec())
    missing = sorted(s for s in schema_sections if s not in body)
    assert missing == [], f"create_issue_body omits required sections: {missing}"
