# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C014-UNIT-003-the-durable-record-carries-the-count
# Acceptance: acc:govern-lifecycle:C014-UNIT-003-the-durable-record-carries-the-count
# WMBT: wmbt:govern-lifecycle:C014
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C014-UNIT-003 — the proof-of-execution baseline records what was not checked.

``.atdd/baselines/validation/<phase>.yaml`` is the durable artifact a later reader
— including #1670's conditional mint — consults to learn that ``atdd validate``
passed. It already records ``skipped_api``, so the file's own design concedes that
"passed" is not the whole claim: *which population was not observed* belongs in the
record.

The marker-deselected population is the larger one and is absent. Today a baseline
written after a run that evaluated 237 of 445 planner validators is byte-identical
in structure to one written after a run that evaluated all 445. stdout is not a
record; this is.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.commands.validation_baseline import (
    validation_baseline_path,
    write_validation_baseline,
)

pytestmark = [pytest.mark.platform]


def _write(tmp_path: Path, **kwargs) -> dict:
    write_validation_baseline(phase="planner", repo_root=tmp_path, **kwargs)
    return yaml.safe_load(validation_baseline_path(tmp_path, "planner").read_text())


def test_a_partial_run_records_the_could_not_check_count_as_data(tmp_path):
    """A reader of the artifact alone can tell a partial run from a complete one."""
    data = _write(tmp_path, could_not_check=208)

    assert data["could_not_check"] == 208


def test_a_complete_run_records_zero_rather_than_omitting_the_field(tmp_path):
    """A missing count must never be ambiguous with a complete run.

    If the key were written only when non-zero, every pre-C014 baseline and every
    complete run would look identical — and the older of the two is the one that
    is not making the claim.
    """
    data = _write(tmp_path, could_not_check=0)

    assert "could_not_check" in data
    assert data["could_not_check"] == 0


def test_a_run_whose_coverage_could_not_be_determined_records_that_it_is_unknown(tmp_path):
    """The probe can itself fail. "Unknown" is not "zero" — this WMBT in miniature."""
    data = _write(tmp_path, could_not_check=None)

    assert "could_not_check" in data
    assert data["could_not_check"] is None


def test_the_fields_the_baseline_already_carried_are_unchanged(tmp_path):
    """Existing readers and the source-hash comparison must be unaffected."""
    data = _write(tmp_path, skipped_api=True, could_not_check=208)

    assert data["phase"] == "planner"
    assert data["skipped_api"] is True
    assert isinstance(data["source_hash"], str) and data["source_hash"]
    assert isinstance(data["passed_at"], str) and data["passed_at"]
    assert isinstance(data["atdd_version"], str) and data["atdd_version"]


def test_the_count_defaults_to_unknown_rather_than_to_zero_for_callers_that_do_not_pass_it(tmp_path):
    """A caller that has not been taught to measure must not assert completeness."""
    data = _write(tmp_path)

    assert "could_not_check" in data
    assert data["could_not_check"] is None
