# URN: test:govern-lifecycle:define-validator-report-and-persistence-materialization-contract:E037-UNIT-001-validator-report-emit-contract
# Acceptance: acc:govern-lifecycle:E037-UNIT-001-validator-report-emit-contract
"""Unit test for E037-UNIT-001 (docs/coach-decomposition.md §4.2, §4.11).

``ValidatorReport`` is the frozen §4.2 contract, re-exported from
``atdd.validators`` as the stable validator-emission location, and
``emit_reports`` appends one run-scoped JSONL row per report while staying a safe
no-op when no run context is configured.
"""
from __future__ import annotations

import dataclasses
import json

import pytest

from atdd.coach.core.types import ValidatorReport as CoreValidatorReport
from atdd.validators import ValidatorReport, emit_reports
from atdd.validators import emit as emit_mod

pytestmark = pytest.mark.atdd_validator

_FIELDS = {
    "validator_id",
    "rule_id",
    "severity",
    "disposition",
    "unsuppressed_count",
    "location",
    "detail",
    "fix_hint_ref",
}


def _sample(**overrides) -> ValidatorReport:
    base = dict(
        validator_id="demo_validator",
        rule_id="demo.rule",
        severity=3,
        disposition="warn-and-log",
        unsuppressed_count=2,
        location="src/x.py:7",
        detail="demo violation",
    )
    base.update(overrides)
    return ValidatorReport(**base)


def test_validator_report_is_the_frozen_core_type():
    # Re-export must be the very same object defined in pure policy (§4.2).
    assert ValidatorReport is CoreValidatorReport
    fields = {f.name for f in dataclasses.fields(ValidatorReport)}
    assert _FIELDS <= fields
    with pytest.raises(dataclasses.FrozenInstanceError):
        _sample().severity = 5  # type: ignore[misc]


def test_emit_reports_writes_one_jsonl_row_per_report(tmp_path, monkeypatch):
    sink = tmp_path / "validator-reports.jsonl"
    monkeypatch.setenv(emit_mod.ENV_REPORTS_PATH, str(sink))
    emit_reports((_sample(rule_id="a"), _sample(rule_id="b", disposition="block")))
    rows = [json.loads(line) for line in sink.read_text().splitlines() if line.strip()]
    assert len(rows) == 2
    assert {row["rule_id"] for row in rows} == {"a", "b"}
    assert set(rows[0]) == _FIELDS  # every §4.2 field round-trips


def test_emit_reports_is_noop_without_run_context(tmp_path, monkeypatch):
    for var in (emit_mod.ENV_REPORTS_PATH, emit_mod.ENV_RUN_DIR, emit_mod.ENV_RUN_ID):
        monkeypatch.delenv(var, raising=False)
    assert emit_mod.resolve_reports_path() is None
    # Must not raise and must not create anything when there is no run context.
    emit_reports((_sample(),))
