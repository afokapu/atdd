# URN: test:observe-and-correct:E003-UNIT-008-schema-deprecation
# Acceptance: acc:observe-and-correct:E003-UNIT-008-schema-deprecation
# WMBT: wmbt:observe-and-correct:E003
# Phase: RED
# Assertion: structural
# Layer: integration
"""E003-UNIT-008 — correction.schema.json marks multiplexer-send with
deprecated:true; the enum value remains valid (C0 frozen) so existing
consumers do not break.

Issue #824.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_SCHEMA_PATH = (
    Path(__file__).parent.parent.parent  # src/atdd/coach
    / "schemas"
    / "correction.schema.json"
)


def test_correction_schema_file_exists():
    assert _SCHEMA_PATH.exists(), f"correction.schema.json not found at {_SCHEMA_PATH}"


def test_multiplexer_send_still_valid_enum_value():
    """multiplexer-send remains in the injection_method enum (C0 frozen, not removed)."""
    with _SCHEMA_PATH.open() as f:
        schema = json.load(f)

    injection_method = schema["properties"]["injection_method"]
    enum_values = injection_method["enum"]

    assert "multiplexer-send" in enum_values, (
        "multiplexer-send was removed from the enum — only deprecation is allowed (C0)"
    )


def test_multiplexer_send_is_annotated_deprecated():
    """multiplexer-send carries a $comment or deprecated annotation in the schema."""
    with _SCHEMA_PATH.open() as f:
        schema = json.load(f)

    injection_method = schema["properties"]["injection_method"]

    # Accept any of: deprecated:true field, or $comment mentioning "deprecated"
    is_deprecated = (
        injection_method.get("deprecated") is True
        or (
            isinstance(injection_method.get("$comment"), str)
            and "deprecated" in injection_method["$comment"].lower()
        )
        or (
            isinstance(injection_method.get("description"), str)
            and "deprecated" in injection_method["description"].lower()
            and "multiplexer-send" in injection_method["description"].lower()
        )
    )

    assert is_deprecated, (
        "multiplexer-send is not annotated as deprecated in correction.schema.json. "
        "Expected: injection_method.deprecated=true or $comment containing 'deprecated'. "
        f"Got: {json.dumps(injection_method, indent=2)}"
    )


def test_cli_return_not_deprecated():
    """cli-return is NOT deprecated."""
    with _SCHEMA_PATH.open() as f:
        schema = json.load(f)

    injection_method = schema["properties"]["injection_method"]
    comment = injection_method.get("$comment", "") or ""
    description = injection_method.get("description", "") or ""

    # cli-return should not appear as deprecated
    assert "cli-return" not in comment.lower().replace("deprecated: multiplexer-send", ""), (
        "cli-return should not be deprecated"
    )


def test_schema_still_validates_multiplexer_send_records():
    """A correction record with injection_method=multiplexer-send still validates."""
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    with _SCHEMA_PATH.open() as f:
        schema = json.load(f)

    record = {
        "agent_id": "test-agent-001",
        "rule_id": "TEST-001",
        "severity": 3,
        "disposition": "pending",
        "correction_text": "test correction",
        "injection_method": "multiplexer-send",
    }

    # Should not raise
    jsonschema.validate(record, schema)
