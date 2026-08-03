"""Runnable enforcement for the four interlocking tester rules (python-pytest).

Two layers, the same shape as the python-pytest fleet detectors
(pytest_test_filename, security_patterns):

  1. DETECTOR SELF-TESTS — pin the decision logic for ALL FOUR rule_ids
     (route-coverage, production-runner-used, smoke-coverage-for-station-master,
     trace-binds-declared-route): the clean fixture emits nothing across every
     rule, and each isolated dirty fixture fires EXACTLY its own rule and no
     other (proving the four checks are independent). Always green.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan ``ATDD_SCAN_ROOTS``
     and write the RAW structured violations to ``ATDD_VIOLATIONS_REPORT`` for
     ``adapter/run.py`` to read back.

CRITICAL — the emission layer does NOT ``assert violations == []``. The detector
emits RAW facts; all four rules are ``strict``, but applying that disposition
(blocking) is the GATE's job (``gates/interlocking-coverage.gate.yaml``), never the
detector's. The emission test passes once it emits.

No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

# The detector lives in ../src (manifest entrypoint: src/interlocking_coverage.py).
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
sys.path.insert(0, str(_SRC))

import interlocking_coverage as detector  # noqa: E402

_FIXTURES = _HERE.parent / "fixtures"

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


def _rule_ids(violations: list[dict]) -> set[str]:
    return {v["rule_id"] for v in violations}


# ── 1a. parsing + shared helpers ──────────────────────────────────────────────


_INTERLOCKING_YAML = """\
schema_version: 1.0.0
interlocking_id: interlocking:match-resolution
entrypoint:
  exposed: true
  actions:
    - resolve_match
routes:
  - route_id: nominal-all-voted
    category: nominal
    category_digit: "0"
    train_id: 3007-match-resolution-standard
  - route_id: alternate-timeout
    category: alternate
    category_digit: "2"
    train_id: 3207-match-resolution-timeout
"""


def test_parse_interlocking_extracts_routes_and_entrypoint() -> None:
    rec = detector.parse_interlocking(_INTERLOCKING_YAML)
    assert rec is not None
    assert rec["interlocking_id"] == "interlocking:match-resolution"
    assert [r["route_id"] for r in rec["routes"]] == ["nominal-all-voted", "alternate-timeout"]
    assert rec["exposed"] is True
    assert rec["actions"] == ["resolve_match"]
    assert rec["routes"][0]["category_digit"] == "0"


def test_parse_ignores_documents_without_route_space() -> None:
    index = "schema_version: 1.0.0\ninterlockings:\n  - ref: interlocking:x\n"
    assert detector.parse_interlocking(index) is None
    assert detector.parse_routes(index) == (None, [])


def test_route_covered_by_route_id_or_train_id() -> None:
    _, routes = detector.parse_routes(_INTERLOCKING_YAML)
    nominal, alternate = routes
    assert detector.is_route_covered(nominal, ["hits nominal-all-voted"]) is True
    assert detector.is_route_covered(alternate, ["runs 3207-match-resolution-timeout"]) is True
    assert detector.is_route_covered(alternate, ["only nominal-all-voted"]) is False
    # identifier-bounded: a longer slug containing the id is not coverage.
    assert detector.is_route_covered(nominal, ["nominal-all-voted-extra"]) is False


def test_missing_trace_fields_distinguishes_category_from_digit() -> None:
    # A source asserting only route_category_digit is still missing route_category.
    src = 'trace["route_category_digit"]'
    missing = detector.missing_trace_fields(src)
    assert "route_category" in missing
    assert "route_category_digit" not in missing


# ── 1b. clean fixture: every rule passes ──────────────────────────────────────


def test_clean_fixture_has_no_violations_across_all_rules() -> None:
    assert detector.scan_root(_FIXTURES / "clean") == []


# ── 1c. each dirty fixture fires EXACTLY its own rule (independence) ───────────


def test_dirty_route_missing_fires_only_route_coverage() -> None:
    v = detector.scan_root(_FIXTURES / "dirty")
    assert _rule_ids(v) == {detector.RULE_ROUTE_COVERAGE}
    assert len(v) == 1
    item = v[0]
    assert "alternate-timeout" in item["evidence"]
    assert item["file"].endswith("match-resolution.yaml")
    assert "route_id: alternate-timeout" in item["source_line"]
    assert "digit '2'" in item["evidence"]
    assert set(item) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}


def test_dirty_mock_runner_fires_only_production_runner() -> None:
    v = detector.scan_root(_FIXTURES / "dirty_mock_runner")
    assert _rule_ids(v) == {detector.RULE_PRODUCTION_RUNNER}
    assert any("patch" in item["evidence"].lower() for item in v)
    for item in v:
        assert item["file"].endswith(".py")
        assert set(item) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}


def test_dirty_smoke_missing_fires_only_smoke() -> None:
    v = detector.scan_root(_FIXTURES / "dirty_smoke_missing")
    assert _rule_ids(v) == {detector.RULE_SMOKE}
    assert len(v) == 1
    item = v[0]
    assert "resolve_match" in item["evidence"]
    assert item["file"].endswith("match-resolution.yaml")


def test_dirty_trace_missing_fires_only_trace() -> None:
    v = detector.scan_root(_FIXTURES / "dirty_trace_missing")
    assert _rule_ids(v) == {detector.RULE_TRACE}
    assert len(v) == 1
    item = v[0]
    # The omitted binding fields are named in the evidence.
    assert "guard_id" in item["evidence"]
    assert "resolution_reason" in item["evidence"]
    assert item["file"].endswith(".py")


def test_every_rule_id_is_proven_by_some_dirty_fixture() -> None:
    seen: set[str] = set()
    for name in ("dirty", "dirty_mock_runner", "dirty_smoke_missing", "dirty_trace_missing"):
        seen |= _rule_ids(detector.scan_root(_FIXTURES / name))
    assert seen == set(detector.ALL_RULE_IDS)


# ── 2. emission (writes the RAW report; does NOT decide disposition) ───────────


def _scan_roots() -> list[Path]:
    raw = os.environ.get(ENV_SCAN_ROOTS)
    if raw:
        try:
            names = json.loads(raw)
        except json.JSONDecodeError:
            names = []
    else:
        names = [str(_FIXTURES / "clean")]
    roots: list[Path] = []
    for n in names:
        p = Path(n)
        roots.append(p if p.is_absolute() else (_HERE / p))
    return roots


def test_emit_raw_interlocking_report() -> None:
    """Scan the supplied roots and emit the RAW violation report (NOT a verdict)."""
    roots = _scan_roots()
    violations = detector.scan_roots(roots)

    report_path = os.environ.get(ENV_REPORT)
    if report_path:
        payload = {
            "contract_version": CONTRACT_VERSION,
            "scan_roots": [str(r) for r in roots],
            "violations": violations,
        }
        Path(report_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Run-health only: deliberately NOT gated on emptiness (disposition is the gate's).
    assert isinstance(violations, list)
