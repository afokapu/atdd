"""Runnable enforcement for the five coder.train.interlocking-* conventions under python-pytest.

Two layers:

  1. DETECTOR SELF-TESTS — pin the AST decision logic against the clean/dirty fixtures. The clean
     interlocking-enabled consumer is silent; each isolation fixture trips exactly one of the five
     rule_ids; the combined dirty fixture trips several; the union across fixtures covers all five.
     These prove each rule_id fires independently.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan ``ATDD_SCAN_ROOTS`` and write the RAW
     structured violations to ``ATDD_VIOLATIONS_REPORT`` for the provider CLI / run.py to read back.

All five rule_ids are ``strict``; this test still only EMITS the RAW violation list. The strict verdict
(any violation -> FAIL) is the downstream consumer's disposition decision, never the detector's.

No core (``atdd.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import interlocking_infrastructure as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent.parent
_FIXTURES = _HERE / "fixtures"

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"

# Each isolation fixture must trip EXACTLY one rule_id — proving the five conventions are independently
# enforced. ``dirty_no_resolve_train`` isolates runner-exists (missing method); ``dirty_missing_runner``
# additionally exercises the missing-class path (runner-exists + the resulting station-routing defect).
_ISOLATION = {
    "dirty_no_resolve_train": {detector.RULE_RUNNER_EXISTS},
    "dirty_bare_resolution": {detector.RULE_RESOLUTION_MODEL},
    "dirty_station_unlinked": {detector.RULE_STATION_ROUTING},
    "dirty_direct_wagon": {detector.RULE_DELEGATES},
    "dirty_cargo": {detector.RULE_NO_CARGO},
}


def _rule_ids(violations: list[dict]) -> set[str]:
    return {v["rule_id"] for v in violations}


def _assert_v11_shape(violations: list[dict]) -> None:
    for v in violations:
        assert set(v) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}
        assert v["rule_id"] in detector.ALL_RULE_IDS
        assert isinstance(v["line"], int) and isinstance(v["col"], int)


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_clean_consumer_has_no_violations() -> None:
    assert detector.scan_root(_FIXTURES / "clean") == []


def test_each_rule_id_fires_independently() -> None:
    # The load-bearing control: one isolation fixture per convention, each tripping exactly its rule_id.
    for fixture, expected in _ISOLATION.items():
        violations = detector.scan_root(_FIXTURES / fixture)
        _assert_v11_shape(violations)
        assert violations, f"{fixture} produced no violations"
        assert _rule_ids(violations) == expected, f"{fixture} -> {_rule_ids(violations)}"


def test_all_five_rule_ids_are_covered() -> None:
    covered: set[str] = set()
    for fixture in [*_ISOLATION, "dirty", "dirty_missing_runner"]:
        covered |= _rule_ids(detector.scan_root(_FIXTURES / fixture))
    assert covered == detector.ALL_RULE_IDS


def test_combined_dirty_fixture_trips_multiple_rules() -> None:
    violations = detector.scan_root(_FIXTURES / "dirty")
    _assert_v11_shape(violations)
    cats = _rule_ids(violations)
    assert {
        detector.RULE_RESOLUTION_MODEL,
        detector.RULE_STATION_ROUTING,
        detector.RULE_DELEGATES,
        detector.RULE_NO_CARGO,
    } <= cats


def test_missing_class_flags_runner_exists() -> None:
    cats = _rule_ids(detector.scan_root(_FIXTURES / "dirty_missing_runner"))
    assert detector.RULE_RUNNER_EXISTS in cats


def test_pure_direct_train_consumer_carries_no_obligation() -> None:
    # A scan root with no interlocking route and no InterlockingRunner -> the rules do not bite.
    assert detector.scan_root(_FIXTURES / "clean" / "does-not-exist") == []


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


def test_emit_raw_infrastructure_report() -> None:
    """Scan the supplied roots and emit the RAW violation report (NOT a verdict)."""
    roots = _scan_roots()
    violations = detector.scan_roots(roots)
    _assert_v11_shape(violations)

    report_path = os.environ.get(ENV_REPORT)
    if report_path:
        payload = {
            "contract_version": CONTRACT_VERSION,
            "scan_roots": [str(r) for r in roots],
            "violations": violations,
        }
        Path(report_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    assert isinstance(violations, list)
