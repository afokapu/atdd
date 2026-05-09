# URN: test:drive-state-machine:coach-state-machine-and-runtime:P001-UNIT-002-judgments-append-only
# Acceptance: acc:drive-state-machine:P001-UNIT-002-judgments-append-only
# WMBT: wmbt:drive-state-machine:P001
# Phase: RED
# Layer: application
"""P001-UNIT-002 — every ``atdd judge`` call writes a record to
``judgments.jsonl`` with ``inputs_hash`` discipline.

Per spec §6.9: "every judgment writes to ``judgments.jsonl``" with
"Inputs hashed by default; full inputs in gitignored cache." The
durable log carries ``inputs_hash``; full inputs go to a gitignored
cache directory under ``.atdd/runtime/`` (which is itself gitignored).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_judgments_log_path_under_runtime_coach(tmp_path):
    from atdd.coach.commands.durability import JudgmentWriter

    writer = JudgmentWriter(runtime_dir=tmp_path)
    expected = tmp_path / "coach" / "judgments.jsonl"
    assert writer.path == expected
    assert writer.path.parent.is_dir()


def test_append_writes_jsonl_record(tmp_path):
    from atdd.coach.commands.durability import JudgmentWriter

    writer = JudgmentWriter(runtime_dir=tmp_path)
    record = {
        "judgment_id": "j1",
        "timestamp": "2026-05-09T13:45:02Z",
        "call_site": "phase-advance",
        "inputs_hash": "sha256:abc123",
        "response": {"ok": True},
        "cached": False,
    }
    writer.append(record)

    records = _read_jsonl(writer.path)
    assert len(records) == 1
    assert records[0]["judgment_id"] == "j1"


def test_required_fields_per_c0_schema(tmp_path):
    """Required: judgment_id, timestamp, call_site, inputs_hash,
    response, cached."""
    from atdd.coach.commands.durability import JudgmentWriter

    writer = JudgmentWriter(runtime_dir=tmp_path)
    record = {
        "judgment_id": "j1",
        "timestamp": "2026-05-09T13:45:02Z",
        "call_site": "phase-advance",
        "inputs_hash": "sha256:abc",
        "response": True,
        "cached": False,
    }
    writer.append(record)

    [rec] = _read_jsonl(writer.path)
    for field in (
        "judgment_id",
        "timestamp",
        "call_site",
        "inputs_hash",
        "response",
        "cached",
    ):
        assert field in rec, f"missing required field: {field}"


def test_call_site_constrained_to_six_v1_surfaces(tmp_path):
    """Per spec §6.9: six call sites — phase-advance,
    violation-suppression, correction-injection, review-disposition,
    escalation, merge-readiness."""
    from atdd.coach.commands.durability import (
        JudgmentWriter,
        SchemaValidationError,
    )

    writer = JudgmentWriter(runtime_dir=tmp_path)

    valid_sites = {
        "phase-advance",
        "violation-suppression",
        "correction-injection",
        "review-disposition",
        "escalation",
        "merge-readiness",
    }
    for i, site in enumerate(valid_sites):
        writer.append(
            {
                "judgment_id": f"j-{i}",
                "timestamp": "2026-05-09T13:45:02Z",
                "call_site": site,
                "inputs_hash": "sha256:x",
                "response": True,
                "cached": False,
            }
        )

    with pytest.raises(SchemaValidationError):
        writer.append(
            {
                "judgment_id": "j-bad",
                "timestamp": "2026-05-09T13:45:02Z",
                "call_site": "not-a-real-site",
                "inputs_hash": "sha256:x",
                "response": True,
                "cached": False,
            }
        )


def test_full_inputs_persisted_to_gitignored_cache_not_log(tmp_path):
    """``inputs_hash`` is a content hash; full inputs go to a cache
    directory; the durable log never carries the raw inputs."""
    from atdd.coach.commands.durability import JudgmentWriter, hash_inputs

    writer = JudgmentWriter(runtime_dir=tmp_path)
    full_inputs = {
        "prompt": "is INIT→PLANNED safe given these violations: ...",
        "context": {"violations": [{"id": "v1"}, {"id": "v2"}]},
    }
    h = hash_inputs(full_inputs)
    assert h.startswith("sha256:")

    writer.append(
        {
            "judgment_id": "j1",
            "timestamp": "2026-05-09T13:45:02Z",
            "call_site": "phase-advance",
            "inputs_hash": h,
            "response": True,
            "cached": False,
        },
        full_inputs=full_inputs,
    )

    [rec] = _read_jsonl(writer.path)
    assert rec["inputs_hash"] == h
    assert "prompt" not in rec
    assert "context" not in rec

    cache_files = list(writer.cache_dir.iterdir())
    assert len(cache_files) == 1
    cached = json.loads(cache_files[0].read_text())
    assert cached == full_inputs


def test_inputs_hash_stable_across_calls():
    from atdd.coach.commands.durability import hash_inputs

    a = hash_inputs({"a": 1, "b": 2})
    b = hash_inputs({"b": 2, "a": 1})
    assert a == b, "hash must be order-independent"

    c = hash_inputs({"a": 1, "b": 3})
    assert a != c
