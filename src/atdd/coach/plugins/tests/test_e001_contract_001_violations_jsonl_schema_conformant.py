# URN: test:dispatch-validators:dispatch-tier-one-validators:E001-CONTRACT-001-violations-jsonl-schema-conformant
# Acceptance: acc:dispatch-validators:E001-CONTRACT-001-violations-jsonl-schema-conformant
# WMBT: wmbt:dispatch-validators:E001
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E001-CONTRACT-001 — every line in violations.jsonl is valid JSON and
validates against ``validator-result.schema.json`` (frozen at C0 by #483).

Required fields per the schema: ``validator_id, rule_id, severity,
disposition, location, detail, suppression_marker``. Optional fields:
``fix_hint_ref, outcome``. ``additionalProperties`` is false, so the plugin
must NOT emit any field beyond the schema.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from jsonschema import Draft202012Validator

import atdd

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
VALIDATOR_RESULT_SCHEMA = (
    ATDD_PKG_DIR / "coach" / "schemas" / "validator-result.schema.json"
)


def _validator() -> Draft202012Validator:
    schema = json.loads(VALIDATOR_RESULT_SCHEMA.read_text())
    return Draft202012Validator(schema)


def _make_session(repo_root: Path) -> Any:
    config = SimpleNamespace(args=[], rootpath=repo_root, workerinput=None)
    return SimpleNamespace(config=config, items=[], _atdd={})


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _run_session_with_violations(tmp_path: Path, monkeypatch, sha: str) -> Path:
    """End-to-end: start the plugin, push a mixed-disposition Violation set
    through ``assert_disposition_satisfied``, finish the session.

    Returns the violations.jsonl path so tests can inspect it.
    """
    from atdd.coach.plugins import violation_collector as plugin
    from atdd.coach.utils import disposition_gate
    from atdd.coach.utils.rule_id_registry import RuleMetadata
    from atdd.coach.validators._violation import Violation

    monkeypatch.setenv("ATDD_VALIDATION_SHA", sha)
    monkeypatch.setenv("ATDD_RUNTIME_DIR", str(tmp_path / "runtime"))

    code = tmp_path / "src/x.py"
    code.parent.mkdir(parents=True, exist_ok=True)
    code.write_text(
        "a\n"
        "print('y')  # atdd:suppress(SC-001) UNTIL=2099-01-01\n"
        "c\n"
    )
    rel = code.relative_to(tmp_path)

    session = _make_session(tmp_path)
    plugin.pytest_sessionstart(session)

    registry = {
        "STRICT-001": RuleMetadata(
            rule_id="STRICT-001",
            convention_path=Path("/dev/null"),
            severity=5,
            description="x",
            disposition="strict",
            fix_hint="recipe:strict#step-1",
        ),
        "SC-001": RuleMetadata(
            rule_id="SC-001",
            convention_path=Path("/dev/null"),
            severity=3,
            description="suppress-and-clean rule",
            disposition="suppress-and-clean",
        ),
        "ADV-001": RuleMetadata(
            rule_id="ADV-001",
            convention_path=Path("/dev/null"),
            severity=1,
            description="advisory rule",
            disposition="advisory",
        ),
    }

    # Strict + with fix_hint_ref
    strict = Violation(
        rule_id="STRICT-001",
        severity=5,
        location=f"{rel}:1",
        detail="strict violation",
        fix_hint_ref="recipe:adapter#step-1",
    )
    suppressed = Violation(
        rule_id="SC-001",
        severity=3,
        location=f"{rel}:2",
        detail="suppressed by inline marker",
    )
    advisory = Violation(
        rule_id="ADV-001",
        severity=1,
        location=f"{rel}:3",
        detail="advisory note",
    )

    disposition_gate.assert_disposition_satisfied(
        validator_id="src/x.py::test_advisory",
        violations=[advisory],
        registry=registry,
        repo_root=tmp_path,
    )
    disposition_gate.assert_disposition_satisfied(
        validator_id="src/x.py::test_sc",
        violations=[suppressed],
        registry=registry,
        repo_root=tmp_path,
    )
    with pytest.raises(pytest.fail.Exception):
        disposition_gate.assert_disposition_satisfied(
            validator_id="src/x.py::test_strict",
            violations=[strict],
            registry=registry,
            repo_root=tmp_path,
        )

    plugin.pytest_sessionfinish(session, exitstatus=1)
    disposition_gate.set_active_pytest_session(None)

    return tmp_path / "runtime" / "validations" / sha / "violations.jsonl"


# ---------------------------------------------------------------------------
# Schema conformance — every line.
# ---------------------------------------------------------------------------


def test_every_line_is_valid_json(tmp_path, monkeypatch):
    out = _run_session_with_violations(tmp_path, monkeypatch, sha="a" * 40)
    assert out.exists(), "violations.jsonl missing"
    for raw in out.read_text().splitlines():
        if not raw.strip():
            continue
        json.loads(raw)  # raises if any line is malformed JSON


def test_every_line_validates_against_schema(tmp_path, monkeypatch):
    out = _run_session_with_violations(tmp_path, monkeypatch, sha="b" * 40)
    validator = _validator()
    for record in _read_jsonl(out):
        errors = list(validator.iter_errors(record))
        assert errors == [], (
            f"record {record.get('rule_id')!r} failed schema: "
            f"{[e.message for e in errors]}"
        )


def test_required_fields_present_on_every_record(tmp_path, monkeypatch):
    out = _run_session_with_violations(tmp_path, monkeypatch, sha="c" * 40)
    required = {
        "validator_id",
        "rule_id",
        "severity",
        "disposition",
        "location",
        "detail",
        "suppression_marker",
    }
    for record in _read_jsonl(out):
        missing = required - set(record.keys())
        assert not missing, f"record {record!r} missing fields {missing}"


def test_no_extra_fields_emitted(tmp_path, monkeypatch):
    """The schema's ``additionalProperties: false`` forbids any field beyond
    what's declared. The plugin must not emit, e.g., legacy or debug fields."""
    out = _run_session_with_violations(tmp_path, monkeypatch, sha="d" * 40)
    allowed = {
        "validator_id",
        "rule_id",
        "severity",
        "disposition",
        "location",
        "detail",
        "suppression_marker",
        "fix_hint_ref",
        "outcome",
    }
    for record in _read_jsonl(out):
        extras = set(record.keys()) - allowed
        assert not extras, f"record {record!r} carries unsupported fields {extras}"


def test_fix_hint_ref_propagates_when_present(tmp_path, monkeypatch):
    """fix_hint_ref is optional — when the source Violation carries it, the
    record must preserve it verbatim."""
    out = _run_session_with_violations(tmp_path, monkeypatch, sha="e" * 40)
    records = _read_jsonl(out)
    strict_records = [r for r in records if r["rule_id"] == "STRICT-001"]
    assert strict_records, "expected at least one STRICT-001 record"
    assert strict_records[0]["fix_hint_ref"] == "recipe:adapter#step-1"


def test_suppression_marker_null_for_unsuppressed_records(tmp_path, monkeypatch):
    """When no inline marker matched, ``suppression_marker`` is the literal
    null sentinel (per schema description)."""
    out = _run_session_with_violations(tmp_path, monkeypatch, sha="f" * 40)
    records = _read_jsonl(out)
    advisory = [r for r in records if r["rule_id"] == "ADV-001"]
    assert advisory and advisory[0]["suppression_marker"] is None


def test_suppression_marker_text_present_when_absorbed(tmp_path, monkeypatch):
    """When a suppress-and-clean violation is absorbed by an inline marker,
    the record carries the marker text (string, not null)."""
    out = _run_session_with_violations(tmp_path, monkeypatch, sha="0" * 40)
    records = _read_jsonl(out)
    sc = [r for r in records if r["rule_id"] == "SC-001"]
    assert sc, "expected SC-001 record"
    marker = sc[0]["suppression_marker"]
    assert isinstance(marker, str)
    assert "atdd:suppress(SC-001)" in marker
