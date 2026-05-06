"""Unit tests for ``atdd.coach.utils.diagnostics`` (issue #449).

Covers:
  * ``Item`` / ``Finding`` / ``ConventionRef`` to_dict() shape.
  * ``fail_with_diagnostic`` empty-items semantics.
  * ``fail_with_diagnostic`` records on the active nodeid.
  * Outside a pytest run (no active nodeid) the helper still calls
    ``pytest.fail`` and the recording is a silent no-op.
"""

from __future__ import annotations

import pytest

from atdd.coach.utils import diagnostics as diag
from atdd.coach.utils.diagnostics import (
    ConventionRef,
    Finding,
    Item,
    LEGAL_CATEGORIES,
    LEGAL_SEVERITIES,
    fail_with_diagnostic,
    get_pending_findings,
    set_active_nodeid,
)


def test_legal_categories_includes_unmigrated_bucket():
    """category=unmigrated must be valid — auto-assigned for non-migrated validators."""
    assert "unmigrated" in LEGAL_CATEGORIES


def test_severity_enum_is_error_warning_only():
    """Severity vocabulary frozen at v1: error | warning."""
    assert LEGAL_SEVERITIES == frozenset({"error", "warning"})


def test_item_to_dict_round_trip():
    item = Item(file="x.py", line=10, symbol="Foo", expected="Bar", found="Foo", fix="Rename Foo to Bar")
    d = item.to_dict()
    assert d["file"] == "x.py"
    assert d["line"] == 10
    assert d["expected"] == "Bar"
    assert d["fix"] == "Rename Foo to Bar"
    assert d["extra"] == {}


def test_convention_ref_to_dict_round_trip():
    ref = ConventionRef(file="conv.yaml", anchor="anchor-1")
    assert ref.to_dict() == {"file": "conv.yaml", "anchor": "anchor-1"}


def test_finding_to_dict_includes_convention_ref_when_present():
    finding = Finding(
        validator_id="t",
        validator_path="path/x.py",
        category="naming",
        severity="error",
        summary="s",
        raw_message="r",
        items=[Item(file="x.py")],
        convention_ref=ConventionRef(file="c.yaml", anchor="a"),
    )
    d = finding.to_dict()
    assert d["convention_ref"] == {"file": "c.yaml", "anchor": "a"}
    assert d["category"] == "naming"
    assert d["raw_message"] == "r"
    assert len(d["items"]) == 1


def test_finding_to_dict_omits_convention_ref_when_none():
    finding = Finding(
        validator_id="t", validator_path=None, category="unmigrated",
        severity="error", summary="s", raw_message="r",
    )
    d = finding.to_dict()
    assert "convention_ref" not in d


def test_fail_with_diagnostic_records_finding_for_active_nodeid():
    diag.clear_pending_findings()
    set_active_nodeid("src/atdd/x/test_y.py::test_z")
    try:
        with pytest.raises(pytest.fail.Exception):
            fail_with_diagnostic(
                "boom",
                category="naming",
                items=[Item(file="x.py", symbol="A", expected="B", found="A", fix="rename")],
                convention_ref=ConventionRef(file="c.yaml", anchor="a"),
            )

        recorded = get_pending_findings("src/atdd/x/test_y.py::test_z")
        assert len(recorded) == 1
        f = recorded[0]
        assert f.category == "naming"
        assert f.validator_id == "test_z"
        assert f.validator_path == "src/atdd/x/test_y.py"
        assert f.summary == "boom"
        assert f.raw_message == "boom"
        assert len(f.items) == 1
        assert f.items[0].symbol == "A"
    finally:
        set_active_nodeid(None)


def test_fail_with_diagnostic_empty_items_is_valid():
    """Issue #449 Phase 1: empty items means structural failure."""
    diag.clear_pending_findings()
    set_active_nodeid("nodeid-empty")
    try:
        with pytest.raises(pytest.fail.Exception):
            fail_with_diagnostic("file missing", category="missing-file")
        recorded = get_pending_findings("nodeid-empty")
        assert len(recorded) == 1
        assert recorded[0].items == []
        assert recorded[0].raw_message == "file missing"
    finally:
        set_active_nodeid(None)


def test_fail_with_diagnostic_outside_pytest_run_is_silent_no_op_recording():
    """Without an active nodeid, fail still raises and no finding is stored."""
    diag.clear_pending_findings()
    set_active_nodeid(None)
    with pytest.raises(pytest.fail.Exception):
        fail_with_diagnostic("orphan", category="hygiene")
    # No nodeid → nothing was stored.
    assert get_pending_findings("anything") == []


def test_fail_with_diagnostic_accepts_dict_items_and_coerces():
    diag.clear_pending_findings()
    set_active_nodeid("dict-items-nodeid")
    try:
        with pytest.raises(pytest.fail.Exception):
            fail_with_diagnostic(
                "dict items",
                category="hygiene",
                items=[{"file": "x.py", "line": 7, "fix": "do thing"}],
            )
        recorded = get_pending_findings("dict-items-nodeid")
        assert recorded[0].items[0].file == "x.py"
        assert recorded[0].items[0].line == 7
    finally:
        set_active_nodeid(None)


def test_fail_with_diagnostic_summary_defaults_to_first_meaningful_line():
    diag.clear_pending_findings()
    set_active_nodeid("summary-nodeid")
    try:
        with pytest.raises(pytest.fail.Exception):
            fail_with_diagnostic(
                "\n\n  one-liner summary\nmore body text\n",
                category="naming",
            )
        recorded = get_pending_findings("summary-nodeid")
        assert recorded[0].summary == "one-liner summary"
    finally:
        set_active_nodeid(None)


def test_fail_with_diagnostic_invalid_severity_falls_back_to_error():
    diag.clear_pending_findings()
    set_active_nodeid("sev-nodeid")
    try:
        with pytest.raises(pytest.fail.Exception):
            fail_with_diagnostic("x", category="naming", severity="catastrophic")
        recorded = get_pending_findings("sev-nodeid")
        assert recorded[0].severity == "error"
    finally:
        set_active_nodeid(None)
