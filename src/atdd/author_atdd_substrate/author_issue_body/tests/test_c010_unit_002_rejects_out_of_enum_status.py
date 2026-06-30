# URN: test:author-atdd-substrate:author-issue-body:C010-UNIT-002-rejects-out-of-enum-status
# Acceptance: acc:author-atdd-substrate:C010-UNIT-002-rejects-out-of-enum-status
# WMBT: wmbt:author-atdd-substrate:C010
# Phase: RED
# Layer: application
"""C010-UNIT-002 — the validator rejects an out-of-enum Metadata Status.

Exercises the single shared vocabulary: the schema's Status enum equals the
phase_machine phases (INIT, PLANNED, RED, GREEN, SMOKE, REFACTOR, COMPLETE,
BLOCKED, OBSOLETE) — the same set the State-Store work-item state carries. A
body whose Status is `DONE` (not in the enum) must fail validation.
"""
from __future__ import annotations

from ._helpers import (
    PHASE_ENUM,
    get_validate_issue_body,
    legacy_compliant_body,
    load_issue_schema,
)


def _status_enum(schema: dict) -> list[str]:
    """Pull the Status enum out of issue.schema.json wherever it is modeled."""
    props = schema.get("properties", {})
    # Tolerate either a flat `status` property or a nested metadata object —
    # the GREEN author decides the exact nesting; both expose an `enum`.
    for key in ("status", "Status"):
        node = props.get(key)
        if isinstance(node, dict) and "enum" in node:
            return list(node["enum"])
    meta = props.get("metadata") or props.get("Issue Metadata") or {}
    sub = (meta.get("properties") or {}) if isinstance(meta, dict) else {}
    for key in ("status", "Status"):
        node = sub.get(key)
        if isinstance(node, dict) and "enum" in node:
            return list(node["enum"])
    raise AssertionError("issue.schema.json exposes no Status enum")


def test_c010_unit_002_rejects_out_of_enum_status():
    schema = load_issue_schema()

    # The shared-vocabulary constraint: schema Status enum == phase_machine phases.
    assert set(_status_enum(schema)) == set(PHASE_ENUM), (
        "Status enum must equal the phase_machine phase vocabulary (no fork)"
    )

    body = legacy_compliant_body().replace("# Sample Compliant Issue", "# Issue\n\nStatus: DONE")
    violations = get_validate_issue_body()(body)

    assert violations, "validator accepted an out-of-enum Status (`DONE`)"
    assert any("status" in v.lower() for v in violations), (
        f"failure does not name the Status enum: {violations}"
    )
