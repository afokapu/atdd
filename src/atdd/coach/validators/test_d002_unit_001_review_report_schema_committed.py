# URN: test:review-phase-boundaries:review-report-schema:D002-UNIT-001-review-report-schema-committed
# Acceptance: acc:review-phase-boundaries:D002-UNIT-001-review-report-schema-committed
# WMBT: wmbt:review-phase-boundaries:D002
# Phase: GREEN
# Layer: backend.unit
# Assertion: structural

"""
D002-UNIT-001 — review-report.schema.json is committed at
``src/atdd/coach/schemas/``, parses as JSON Schema draft-2020-12, and
declares all required fields per spec §7.4.

Phase RED: fails on a tree where the schema has not been added.
Phase GREEN: schema exists with correct shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Set

import pytest

import atdd

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
SCHEMAS_DIR = ATDD_PKG_DIR / "coach" / "schemas"
SCHEMA_FILE = SCHEMAS_DIR / "review-report.schema.json"

DRAFT_2020_12_URI = "https://json-schema.org/draft/2020-12/schema"

# Required top-level fields per spec §7.4.
REQUIRED_TOP_LEVEL = {
    "review_id",
    "target_commit",
    "reviewer_agent_id",
    "wmbt_urn",
    "phase",
    "verdict",
    "tier1_risk_score",
    "findings",
    "ac_coverage",
    "summary",
}

# Required fields on each findings[] entry.
REQUIRED_FINDING_FIELDS = {
    "rule_id",
    "severity",
    "surface",
    "location",
    "acceptance_ref",
    "description",
    "evidence",
}

# Allowed surface values.
SURFACE_VALUES = {"convention", "task", "semantic", "architecture"}

# Allowed verdict values.
VERDICT_VALUES = {"pass", "concern", "fail"}

# Allowed ac_coverage status values.
COVERAGE_VALUES = {"covered", "not_covered", "partial"}


def _load() -> Dict[str, Any]:
    assert SCHEMA_FILE.exists(), (
        f"Schema not found: {SCHEMA_FILE}. "
        f"Acceptance D002-UNIT-001 requires review-report.schema.json."
    )
    with SCHEMA_FILE.open() as fh:
        return json.load(fh)


def test_schema_file_exists() -> None:
    """review-report.schema.json is committed at src/atdd/coach/schemas/."""
    assert SCHEMA_FILE.exists(), (
        f"Missing schema: {SCHEMA_FILE}. Spec §7.4 requires this schema."
    )


def test_schema_declares_draft_2020_12() -> None:
    """Schema declares ``$schema`` = JSON Schema draft-2020-12."""
    schema = _load()
    assert schema.get("$schema") == DRAFT_2020_12_URI, (
        f"$schema must be {DRAFT_2020_12_URI!r}, "
        f"got {schema.get('$schema')!r}."
    )


def test_schema_parses_as_jsonschema() -> None:
    """Schema is well-formed against the draft-2020-12 meta-schema."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = _load()
    jsonschema.Draft202012Validator.check_schema(schema)


def test_schema_declares_required_top_level_fields() -> None:
    """Schema's ``required`` covers all spec §7.4 top-level fields."""
    schema = _load()
    declared = set(schema.get("required") or ())
    missing = REQUIRED_TOP_LEVEL - declared
    assert not missing, (
        f"Missing required top-level fields: {sorted(missing)}. "
        f"Spec §7.4 requires: {sorted(REQUIRED_TOP_LEVEL)}."
    )


def test_schema_declares_verdict_enum() -> None:
    """``verdict`` is one of pass|concern|fail."""
    schema = _load()
    verdict = schema.get("properties", {}).get("verdict", {})
    enum = verdict.get("enum")
    assert enum is not None, "properties.verdict.enum is missing."
    assert set(enum) == VERDICT_VALUES, (
        f"verdict enum {enum} != {sorted(VERDICT_VALUES)}."
    )


def test_schema_declares_phase_enum() -> None:
    """``phase`` is one of the ATDD lifecycle phases."""
    schema = _load()
    phase = schema.get("properties", {}).get("phase", {})
    enum = phase.get("enum")
    assert enum is not None, "properties.phase.enum is missing."
    assert set(enum) == {"RED", "GREEN", "SMOKE", "REFACTOR"}, (
        f"phase enum {enum} does not match ATDD lifecycle phases."
    )


def test_findings_entry_declares_required_fields() -> None:
    """Each findings[] entry declares all required sub-fields per spec §7.4."""
    schema = _load()
    defs = schema.get("$defs", {})
    finding_def = defs.get("finding", {})
    declared = set(finding_def.get("required") or [])
    missing = REQUIRED_FINDING_FIELDS - declared
    assert not missing, (
        f"finding definition missing required fields: {sorted(missing)}. "
        f"Spec §7.4 requires: {sorted(REQUIRED_FINDING_FIELDS)}."
    )


def test_findings_rule_id_is_nullable() -> None:
    """``rule_id`` on findings[] is nullable (string | null)."""
    schema = _load()
    finding_props = schema.get("$defs", {}).get("finding", {}).get("properties", {})
    rule_id = finding_props.get("rule_id", {})
    assert rule_id.get("type") == ["string", "null"], (
        f"finding.rule_id type must be ['string', 'null'], got {rule_id.get('type')}."
    )


def test_findings_severity_is_integer_1_to_5() -> None:
    """``severity`` on findings[] is integer 1..5."""
    schema = _load()
    finding_props = schema.get("$defs", {}).get("finding", {}).get("properties", {})
    severity = finding_props.get("severity", {})
    assert severity.get("type") == "integer", (
        f"finding.severity type must be integer, got {severity.get('type')}."
    )
    assert severity.get("minimum") == 1 and severity.get("maximum") == 5, (
        f"finding.severity must constrain to [1, 5]."
    )


def test_findings_surface_enum() -> None:
    """``surface`` on findings[] is one of convention|task|semantic|architecture."""
    schema = _load()
    finding_props = schema.get("$defs", {}).get("finding", {}).get("properties", {})
    surface = finding_props.get("surface", {})
    enum = surface.get("enum")
    assert enum is not None, "finding.surface.enum is missing."
    assert set(enum) == SURFACE_VALUES, (
        f"finding.surface enum {enum} != {sorted(SURFACE_VALUES)}."
    )


def test_findings_disposition_enum() -> None:
    """``disposition`` on findings[] uses the frozen vocabulary."""
    schema = _load()
    finding_props = schema.get("$defs", {}).get("finding", {}).get("properties", {})
    disposition = finding_props.get("disposition", {})
    enum = disposition.get("enum")
    assert enum is not None, "finding.disposition.enum is missing."
    expected = {"strict", "suppress-and-clean", "advisory", "documentation-only"}
    assert set(enum) == expected, (
        f"finding.disposition enum {enum} != {sorted(expected)}."
    )


def test_ac_coverage_pattern() -> None:
    """``ac_coverage`` is a map of acc: URN to covered|not_covered|partial."""
    schema = _load()
    ac_coverage = schema.get("properties", {}).get("ac_coverage", {})
    assert ac_coverage.get("type") == "object", (
        "ac_coverage must be type object."
    )
    # Check patternProperties for acc: keys
    pattern_props = ac_coverage.get("patternProperties", {})
    assert "^acc:" in pattern_props, (
        "ac_coverage.patternProperties must include '^acc:' pattern."
    )
    acc_def = pattern_props["^acc:"]
    enum = acc_def.get("enum")
    assert enum is not None, "ac_coverage value enum is missing."
    assert set(enum) == COVERAGE_VALUES, (
        f"ac_coverage enum {enum} != {sorted(COVERAGE_VALUES)}."
    )


def test_schema_disallows_additional_properties() -> None:
    """Top-level ``additionalProperties: false`` per spec §7.4."""
    schema = _load()
    assert schema.get("additionalProperties") is False, (
        "Schema must set additionalProperties: false."
    )
