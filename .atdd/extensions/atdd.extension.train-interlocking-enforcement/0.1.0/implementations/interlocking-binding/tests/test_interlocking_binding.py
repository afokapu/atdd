"""Runnable enforcement for the bilateral-binding convention under python-pytest.

Two layers, the same shape as the sibling interlocking detectors:

  1. DETECTOR SELF-TESTS — pin the decision logic for ALL FIVE binding directions
     (declaration_to_runtime, runtime_to_declaration, station_to_declaration,
     declaration_to_station, trace_to_declaration) plus the parallel-reachability
     schema-drift signal. The complete-closure ``pass/`` fixture emits nothing; each
     ``fail/`` fixture fires EXACTLY its own direction and no other (proving the
     directions are independently bound). The five required-validator test names
     match the convention's `bidirectional[].validator` entries.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan ``ATDD_SCAN_ROOTS`` and
     write the RAW structured violations to ``ATDD_VIOLATIONS_REPORT`` for the
     provider CLI / run.py to read back.

CRITICAL — the emission layer does NOT ``assert violations == []``. The detector emits
RAW facts; the rule is ``strict``, but applying that disposition (blocking) is the
GATE's job (``gates/interlocking-binding.gate.yaml``), never the detector's.

No core (``atdd.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# The detector lives in ../src (manifest entrypoint: src/interlocking_binding.py).
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
sys.path.insert(0, str(_SRC))

import interlocking_binding as detector  # noqa: E402

_FIXTURES = _HERE.parent / "fixtures"
_PASS = _FIXTURES / "pass" / "bilateral_binding_complete"
_FAIL = _FIXTURES / "fail"

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


def _directions(violations: list[dict]) -> set[str]:
    """The binding direction of each RAW violation (the stable evidence prefix token)."""
    return {v["evidence"].split(":", 1)[0] for v in violations}


def _assert_v11_shape(violations: list[dict]) -> None:
    for v in violations:
        assert set(v) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}
        assert v["rule_id"] == detector.RULE_BILATERAL
        assert isinstance(v["line"], int) and isinstance(v["col"], int)


# ── 1a. parsing + helpers ─────────────────────────────────────────────────────


def test_parse_interlocking_consumes_core_entrypoint_field() -> None:
    rec = detector.parse_interlocking(
        (_PASS / "plan/_trains/_interlockings/match-resolution.yaml").read_text()
    )
    assert rec is not None
    assert rec["interlocking_id"] == "interlocking:match-resolution"
    assert rec["exposed"] is True  # core #1248 entrypoint.exposed
    assert rec["actions"] == ["resolve_match"]  # core #1248 entrypoint.actions
    assert rec["parallel_fields"] == []  # no forked reachability field
    assert rec["routes"][0]["train_path"] == "plan/_trains/3007-match-resolution-standard.yaml"


def test_parse_journey_map_classifies_interlocking_and_direct() -> None:
    journey = detector.parse_journey_map((_PASS / "python/app.py").read_text())
    assert journey["resolve_match"]["kind"] == "interlocking"
    assert journey["resolve_match"]["interlocking_id"] == "interlocking:match-resolution"
    assert journey["start_match"]["kind"] == "direct"


def test_parallel_field_detected_in_parse() -> None:
    rec = detector.parse_interlocking(
        (_FAIL / "parallel_reachability_field_used/plan/_trains/_interlockings/match-resolution.yaml").read_text()
    )
    assert rec is not None
    assert "runtime_exposure" in rec["parallel_fields"]
    assert "station_actions" in rec["parallel_fields"]


# ── 1b. complete-closure pass fixture: every direction holds ───────────────────


def test_complete_closure_fixture_has_no_violations() -> None:
    assert detector.scan_root(_PASS) == []


# ── 1c. the FIVE required validators — each direction fails independently ───────


def test_declared_interlocking_routes_are_runtime_resolvable() -> None:
    # declaration_to_runtime: a declared route whose train artifact is absent is unresolvable.
    clean = detector.scan_root(_PASS)
    assert detector.DIR_DECL_RUNTIME not in _directions(clean)

    v = detector.scan_root(_FAIL / "declared_route_not_runtime_resolvable")
    _assert_v11_shape(v)
    assert _directions(v) == {detector.DIR_DECL_RUNTIME}
    assert len(v) == 1
    assert "nominal-all-voted" in v[0]["evidence"]
    assert v[0]["file"].endswith("match-resolution.yaml")


def test_runtime_interlocking_resolution_is_declared() -> None:
    # runtime_to_declaration: the runtime must not resolve a route absent from the loaded YAML.
    assert detector.DIR_RUNTIME_DECL not in _directions(detector.scan_root(_PASS))

    v = detector.scan_root(_FAIL / "runtime_resolves_hidden_route")
    _assert_v11_shape(v)
    assert _directions(v) == {detector.DIR_RUNTIME_DECL}
    assert any("ghost-route-not-declared" in item["evidence"] for item in v)
    assert all(item["file"].endswith("runtime.py") for item in v)


def test_station_master_interlocking_entries_resolve_artifacts() -> None:
    # station_to_declaration: a JOURNEY_MAP interlocking mapping must point to an existing YAML.
    assert detector.DIR_STATION_DECL not in _directions(detector.scan_root(_PASS))

    v = detector.scan_root(_FAIL / "station_master_points_missing_interlocking")
    _assert_v11_shape(v)
    assert _directions(v) == {detector.DIR_STATION_DECL}
    assert len(v) == 1
    assert "does-not-exist.yaml" in v[0]["evidence"]
    assert v[0]["file"].endswith("app.py")


def test_runtime_exposed_interlockings_are_station_master_reachable_or_non_entrypoint() -> None:
    # declaration_to_station: an entrypoint.exposed:true interlocking must be reachable via a wired
    # entrypoint.action; an exposed:false (non-entrypoint) interlocking carries no such obligation.
    assert detector.DIR_DECL_STATION not in _directions(detector.scan_root(_PASS))

    v = detector.scan_root(_FAIL / "exposed_interlocking_unreachable")
    _assert_v11_shape(v)
    assert _directions(v) == {detector.DIR_DECL_STATION}
    assert len(v) == 1
    assert "resolve_match" in v[0]["evidence"]
    assert "exposed" in v[0]["evidence"]
    assert v[0]["file"].endswith("match-resolution.yaml")


def test_interlocking_trace_binds_declared_route() -> None:
    # trace_to_declaration: an asserted trace route_id/interlocking_id must resolve to a declared route.
    assert detector.DIR_TRACE_DECL not in _directions(detector.scan_root(_PASS))

    v = detector.scan_root(_FAIL / "trace_does_not_resolve_to_yaml")
    _assert_v11_shape(v)
    assert _directions(v) == {detector.DIR_TRACE_DECL}
    assert len(v) == 1
    assert "phantom-route-not-in-yaml" in v[0]["evidence"]
    assert v[0]["file"].endswith(".py")


# ── 1d. parallel reachability field is rejected as schema drift ────────────────


def test_parallel_reachability_field_is_rejected_as_schema_drift() -> None:
    assert detector.DIR_PARALLEL_FIELD not in _directions(detector.scan_root(_PASS))

    v = detector.scan_root(_FAIL / "parallel_reachability_field_used")
    _assert_v11_shape(v)
    assert _directions(v) == {detector.DIR_PARALLEL_FIELD}
    assert {item["evidence"].split(":", 1)[0] for item in v} == {detector.DIR_PARALLEL_FIELD}
    joined = " ".join(item["evidence"] for item in v)
    assert "runtime_exposure" in joined and "station_actions" in joined
    assert all(item["file"].endswith("match-resolution.yaml") for item in v)


# ── 1e. every direction is proven by exactly one fail fixture ──────────────────


def test_every_binding_direction_is_proven_by_one_fixture() -> None:
    expected = {
        "declared_route_not_runtime_resolvable": detector.DIR_DECL_RUNTIME,
        "runtime_resolves_hidden_route": detector.DIR_RUNTIME_DECL,
        "station_master_points_missing_interlocking": detector.DIR_STATION_DECL,
        "exposed_interlocking_unreachable": detector.DIR_DECL_STATION,
        "trace_does_not_resolve_to_yaml": detector.DIR_TRACE_DECL,
        "parallel_reachability_field_used": detector.DIR_PARALLEL_FIELD,
    }
    seen: set[str] = set()
    for name, direction in expected.items():
        dirs = _directions(detector.scan_root(_FAIL / name))
        assert dirs == {direction}, f"{name} -> {dirs}"
        seen |= dirs
    assert seen == set(detector.ALL_DIRECTIONS)
    # All RAW violations carry the single bilateral rule_id.
    assert detector.ALL_RULE_IDS == (detector.RULE_BILATERAL,)


def test_non_interlocking_tree_carries_no_obligation() -> None:
    assert detector.scan_root(_PASS / "does-not-exist") == []


# ── 2. emission (writes the RAW report; does NOT decide disposition) ───────────


def _scan_roots() -> list[Path]:
    raw = os.environ.get(ENV_SCAN_ROOTS)
    if raw:
        try:
            names = json.loads(raw)
        except json.JSONDecodeError:
            names = []
    else:
        names = [str(_PASS)]
    roots: list[Path] = []
    for n in names:
        p = Path(n)
        roots.append(p if p.is_absolute() else (_HERE / p))
    return roots


def test_emit_raw_bilateral_binding_report() -> None:
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
