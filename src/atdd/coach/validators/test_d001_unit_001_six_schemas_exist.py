# URN: test:freeze-runtime-contracts:runtime-schema-freeze:D001-UNIT-001-six-schemas-exist
# Acceptance: acc:freeze-runtime-contracts:D001-UNIT-001-six-schemas-exist
# WMBT: wmbt:freeze-runtime-contracts:D001
# Phase: RED
# Layer: backend.integration
# Assertion: structural

"""
D001-UNIT-001 — All six coach v9 runtime schemas exist at
``src/atdd/coach/schemas/``, parse as JSON Schema draft-2020-12, declare
the required fields per spec §C0, and (for ``runtime-event``) enumerate
the 12 event types; ``validator-result`` aligns with substrate's
``Violation`` dataclass.

Phase RED: fails on a tree where no schemas have been added; phase GREEN
when all six schemas land.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

import atdd

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
SCHEMAS_DIR = ATDD_PKG_DIR / "coach" / "schemas"

# The six schemas frozen at C0. Order is the order in spec §C0.
SCHEMA_FILES = (
    "runtime-event.schema.json",
    "coach-decision.schema.json",
    "coach-judgment.schema.json",
    "correction.schema.json",
    "validator-result.schema.json",
    "risk-score.schema.json",
)

# The 12 runtime-event types frozen by spec §C0 (D004 context_clarifier).
EVENT_TYPES = (
    "agent_spawned",
    "heartbeat",
    "commit_observed",
    "event_emitted",
    "escalation_emitted",
    "pr_opened",
    "pr_closed",
    "validation_pending",
    "validation_complete",
    "review_complete",
    "correction_emitted",
    "process_silence",
)

# Per spec §C0 / issue body, the required fields each schema must declare.
REQUIRED_FIELDS: Dict[str, tuple] = {
    "runtime-event.schema.json": ("event_type", "timestamp", "payload"),
    "coach-decision.schema.json": (
        "decision_id",
        "timestamp",
        "coach_run_id",
        "issue_number",
        "decision_type",
        "inputs",
        "outcome",
    ),
    "coach-judgment.schema.json": (
        "judgment_id",
        "timestamp",
        "call_site",
        "inputs_hash",
        "response",
        "cached",
    ),
    "correction.schema.json": (
        "agent_id",
        "rule_id",
        "severity",
        "disposition",
        "correction_text",
        "injection_method",
    ),
    "validator-result.schema.json": (
        "validator_id",
        "rule_id",
        "severity",
        "disposition",
        "location",
        "detail",
        "suppression_marker",
    ),
    "risk-score.schema.json": (
        "sum",
        "by_severity",
        "by_archetype",
        "by_disposition",
        "stale_suppressions",
    ),
}

DRAFT_2020_12_URI = "https://json-schema.org/draft/2020-12/schema"


def _load(name: str) -> Dict[str, Any]:
    path = SCHEMAS_DIR / name
    assert path.exists(), (
        f"Schema not found: {path}. "
        f"Acceptance D001-UNIT-001 requires all six schemas at "
        f"src/atdd/coach/schemas/."
    )
    with path.open() as fh:
        return json.load(fh)


@pytest.mark.parametrize("schema_name", SCHEMA_FILES)
def test_schema_exists(schema_name: str) -> None:
    """Each of the six schemas is committed at src/atdd/coach/schemas/."""
    path = SCHEMAS_DIR / schema_name
    assert path.exists(), (
        f"Missing schema: {path}. C0 freezes six runtime artifact "
        f"contracts; this one is required."
    )


@pytest.mark.parametrize("schema_name", SCHEMA_FILES)
def test_schema_declares_draft_2020_12(schema_name: str) -> None:
    """Each schema declares ``$schema`` = JSON Schema draft-2020-12."""
    schema = _load(schema_name)
    assert schema.get("$schema") == DRAFT_2020_12_URI, (
        f"{schema_name}: $schema must be {DRAFT_2020_12_URI!r}, "
        f"got {schema.get('$schema')!r}. The whole schema set is "
        f"frozen on draft-2020-12 to keep parsers consistent across "
        f"the six coach v9 tracks."
    )


@pytest.mark.parametrize("schema_name", SCHEMA_FILES)
def test_schema_parses_as_jsonschema(schema_name: str) -> None:
    """Each schema is itself well-formed against the draft-2020-12 meta-schema."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = _load(schema_name)
    # Will raise if the schema body is malformed against the meta-schema.
    jsonschema.Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("schema_name", SCHEMA_FILES)
def test_schema_declares_required_fields(schema_name: str) -> None:
    """Each schema's ``required`` list covers the spec §C0 fields."""
    schema = _load(schema_name)
    expected = set(REQUIRED_FIELDS[schema_name])
    declared = set(schema.get("required") or ())
    missing = expected - declared
    assert not missing, (
        f"{schema_name}: missing required fields {sorted(missing)}. "
        f"Spec §C0 requires {sorted(expected)}."
    )


def test_runtime_event_enumerates_12_event_types() -> None:
    """``runtime-event.schema.json`` enumerates the 12 event types from spec §C0."""
    schema = _load("runtime-event.schema.json")
    props = schema.get("properties") or {}
    event_type = props.get("event_type") or {}
    enum = event_type.get("enum")
    assert enum is not None, (
        "runtime-event.schema.json: properties.event_type.enum is missing. "
        "Spec §C0 freezes 12 event types as an enum so cross-track "
        "consumers cannot drift."
    )
    assert sorted(enum) == sorted(EVENT_TYPES), (
        f"runtime-event.schema.json: event_type enum {sorted(enum)} "
        f"does not match the 12 spec §C0 types {sorted(EVENT_TYPES)}."
    )


def test_validator_result_aligns_with_substrate_violation() -> None:
    """``validator-result.schema.json`` carries every substrate ``Violation`` field.

    Substrate's ``Violation`` dataclass exposes ``rule_id``, ``severity``,
    ``location``, ``detail``, and ``fix_hint_ref`` (optional). The C0
    contract adds ``validator_id``, ``disposition``, and ``suppression_marker``
    on top of those — but must not drop any substrate field, so a
    serialized ``Violation`` round-trips through the C0 schema.
    """
    schema = _load("validator-result.schema.json")
    props = schema.get("properties") or {}
    # Required fields on validator-result include the substrate-aligned set.
    for substrate_field in ("rule_id", "severity", "location", "detail"):
        assert substrate_field in props, (
            f"validator-result.schema.json: missing property "
            f"{substrate_field!r}; the schema must align with "
            f"substrate's Violation dataclass."
        )
    # severity is integer 1..5 to match Violation.__post_init__.
    sev = props["severity"]
    assert sev.get("type") == "integer", (
        "validator-result.schema.json: severity must be integer to "
        "align with substrate.Violation.severity."
    )
    assert sev.get("minimum") == 1 and sev.get("maximum") == 5, (
        "validator-result.schema.json: severity must constrain to "
        "[1, 5] to align with substrate.Violation.__post_init__."
    )
