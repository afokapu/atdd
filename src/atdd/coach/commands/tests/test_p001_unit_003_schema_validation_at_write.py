# URN: test:drive-state-machine:coach-state-machine-and-runtime:P001-UNIT-003-schema-validation-at-write
# Acceptance: acc:drive-state-machine:P001-UNIT-003-schema-validation-at-write
# WMBT: wmbt:drive-state-machine:P001
# Phase: RED
# Layer: application
"""P001-UNIT-003 — schema validation runs at write time; malformed
records are rejected before any bytes hit the file.

The error names the missing/invalid field; the file is not partially
written.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_decision_write_rejects_missing_required_field(tmp_path):
    from atdd.coach.commands.durability import (
        DecisionWriter,
        SchemaValidationError,
    )

    writer = DecisionWriter(runtime_dir=tmp_path)
    invalid = {
        "decision_id": "d1",
        "timestamp": "2026-05-09T13:45:02Z",
        # missing coach_run_id
        "issue_number": 498,
        "decision_type": "phase-transition",
        "inputs": {},
        "outcome": {},
    }
    with pytest.raises(SchemaValidationError) as exc_info:
        writer.append(invalid)
    assert "coach_run_id" in str(exc_info.value)
    assert not writer.path.exists() or writer.path.read_text() == ""


def test_decision_write_rejects_wrong_type(tmp_path):
    from atdd.coach.commands.durability import (
        DecisionWriter,
        SchemaValidationError,
    )

    writer = DecisionWriter(runtime_dir=tmp_path)
    invalid = {
        "decision_id": "d1",
        "timestamp": "2026-05-09T13:45:02Z",
        "coach_run_id": "r",
        "issue_number": "not-an-int",
        "decision_type": "phase-transition",
        "inputs": {},
        "outcome": {},
    }
    with pytest.raises(SchemaValidationError) as exc_info:
        writer.append(invalid)
    assert "issue_number" in str(exc_info.value)


def test_judgment_write_rejects_missing_required_field(tmp_path):
    from atdd.coach.commands.durability import (
        JudgmentWriter,
        SchemaValidationError,
    )

    writer = JudgmentWriter(runtime_dir=tmp_path)
    invalid = {
        "judgment_id": "j1",
        "timestamp": "2026-05-09T13:45:02Z",
        # missing call_site
        "inputs_hash": "sha256:x",
        "response": True,
        "cached": False,
    }
    with pytest.raises(SchemaValidationError) as exc_info:
        writer.append(invalid)
    assert "call_site" in str(exc_info.value)
    assert not writer.path.exists() or writer.path.read_text() == ""


def test_file_not_partially_written_after_rejection(tmp_path):
    """If a record is invalid, the file must not contain any partial
    bytes from that record."""
    from atdd.coach.commands.durability import (
        DecisionWriter,
        SchemaValidationError,
    )

    writer = DecisionWriter(runtime_dir=tmp_path)
    valid = {
        "decision_id": "d1",
        "timestamp": "2026-05-09T13:45:02Z",
        "coach_run_id": "r",
        "issue_number": 498,
        "decision_type": "phase-transition",
        "inputs": {},
        "outcome": {},
    }
    writer.append(valid)
    contents_before = writer.path.read_text()

    with pytest.raises(SchemaValidationError):
        writer.append({"decision_id": "bad"})  # missing many required fields

    contents_after = writer.path.read_text()
    assert contents_after == contents_before, (
        "rejected record must not leave bytes in the file"
    )
