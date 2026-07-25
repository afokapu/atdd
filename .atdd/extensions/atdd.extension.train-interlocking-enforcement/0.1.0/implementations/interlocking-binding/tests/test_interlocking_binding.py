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
        "layout_unresolved_no_runtime_or_station": detector.DIR_LAYOUT_UNRESOLVED,
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


# ── 1f. scan layout is resolved from selectors (override / scope / defaults) ────

_LAYOUT = _FIXTURES / "layout"
_SRC_RUNTIME_LAYOUT = _LAYOUT / "runtime_in_src_layout"


def test_default_layout_equals_today_hardcoded_constants(monkeypatch) -> None:
    # Behavior-preserving: with no env override, the resolved layout (from the shipped scope file)
    # MUST equal today's hardcoded constants — this is what keeps every game-app fixture green.
    monkeypatch.delenv(detector.ENV_LAYOUT, raising=False)
    layout = detector._resolve_layout(_PASS)
    assert layout[detector.SEL_INTERLOCKING] == list(detector._INTERLOCKING_GLOBS)
    assert layout[detector.SEL_RUNTIME] == ["python/trains/**/*.py"]
    assert layout[detector.SEL_STATION] == ["python/app.py"]
    assert layout[detector.SEL_E2E] == [detector._E2E_GLOB]
    assert layout[detector.SEL_TRAIN] == [f"{detector._TRAIN_DIR}/**/*.yaml"]


def test_per_repo_override_reads_runtime_at_configured_layout(monkeypatch) -> None:
    # A per-repo ATDD_INTERLOCKING_LAYOUT override pointing python_runtime at src/**/runtime/
    # interlocking/ makes the detector read the runtime that lives THERE (not python/trains/), so its
    # hidden route (declared in no YAML) is caught as runtime_to_declaration.
    monkeypatch.setenv(
        detector.ENV_LAYOUT,
        json.dumps({"python_runtime": ["src/**/runtime/interlocking/**/*.py"]}),
    )
    v = detector.scan_root(_SRC_RUNTIME_LAYOUT)
    _assert_v11_shape(v)
    assert detector.DIR_RUNTIME_DECL in _directions(v)
    assert any("ghost-route-not-declared" in item["evidence"] for item in v)
    assert any(item["file"].endswith("runtime.py") for item in v)


def test_without_override_configured_runtime_is_invisible_and_scan_fails_closed(monkeypatch) -> None:
    # Same tree, DEFAULT layout: the src/ runtime is never read (python/trains/ is empty), there is no
    # Station Master — so instead of a silent green pass the detector fails closed.
    monkeypatch.delenv(detector.ENV_LAYOUT, raising=False)
    v = detector.scan_root(_SRC_RUNTIME_LAYOUT)
    _assert_v11_shape(v)
    assert _directions(v) == {detector.DIR_LAYOUT_UNRESOLVED}


def test_layout_unresolved_fires_when_runtime_and_station_resolve_to_nothing() -> None:
    # Fail-closed teeth: interlockings declared but the resolved runtime AND Station Master globs match
    # NO file → ONE layout_unresolved violation (replaces the old silent no-op).
    v = detector.scan_root(_FAIL / "layout_unresolved_no_runtime_or_station")
    _assert_v11_shape(v)
    assert _directions(v) == {detector.DIR_LAYOUT_UNRESOLVED}
    assert len(v) == 1
    assert "no runtime/Station Master found at configured layout" in v[0]["evidence"]


def test_train_id_fallback_ignores_interlocking_control_artifact(tmp_path) -> None:
    # Regression (adversarial review R3): the recursive train_yaml default
    # (plan/_trains/**/*.yaml) must NOT accept an _interlockings/<id>.yaml control
    # artifact as the route's train (core afokapu/atdd#1504). A route whose
    # train_id equals an interlocking stem, with no real train file, MUST still
    # fire declaration_to_runtime (fail-closed) — not be silently resolved.
    il = tmp_path / "plan" / "_trains" / "_interlockings"
    il.mkdir(parents=True)
    (il / "match-resolution.yaml").write_text(
        "interlocking_id: interlocking:match-resolution\n"
        "routes:\n- route_id: r1\n  train_id: match-resolution\n",
        encoding="utf-8",
    )
    v = detector.scan_root(tmp_path)
    assert detector.DIR_DECL_RUNTIME in _directions(v), (
        "declaration_to_runtime must fire: no real train file exists, only an "
        "_interlockings/ control artifact sharing the train_id stem"
    )


def test_malformed_override_falls_back_to_defaults(monkeypatch) -> None:
    # A non-JSON override must not crash the scan — it falls back to scope/defaults.
    monkeypatch.setenv(detector.ENV_LAYOUT, "{not-json")
    layout = detector._resolve_layout(_PASS)
    assert layout[detector.SEL_RUNTIME] == ["python/trains/**/*.py"]
    assert detector.scan_root(_PASS) == []


# ── 1g. atdd's idiom — function-based Station Master + variable-built resolutions ──
#
# atdd's runtime (core #1251) does NOT use the game-app idiom: the Station Master is the
# FUNCTION `resolve_journey(journey_map, action)` (map is a parameter, no module-level
# JOURNEY_MAP literal), and InterlockingResolution(...) is built from VARIABLES
# (`route_id=route.route_id`), not string literals. These pin the matcher adaptation that
# teaches the detector atdd's idiom while leaving the game-app path (1a–1f) untouched.
#
# The idiom is reproduced INLINE below (portable — no dependency on a sibling core checkout). The
# real dogfood binding to atdd's actual runtime happens in STEP 3 (running the detector against the
# repo), not here — these unit tests stay hermetic.

# Faithful reproduction of atdd's station_master.py idiom: the Station Master is a FUNCTION; the
# journey map is a PARAMETER. No module-level JOURNEY_MAP literal, no call site handing it a map.
_ATDD_STATION_MASTER = (
    "def resolve_journey(journey_map, action):\n"
    "    if action not in journey_map:\n"
    "        raise StationMasterError(action)\n"
    "    mapping = journey_map[action]\n"
    "    return mapping\n"
)

# Faithful reproduction of atdd's runner.py idiom: resolution built from `route.<attr>` where
# `route = interlocking.route_by_id(route_id)` — variables, not string literals.
_ATDD_RUNNER = (
    "def resolve_train(self, action, inputs, state=None):\n"
    "    interlocking = self._load_and_validate()\n"
    "    route_id = evaluate_interlocking_route(interlocking, action, inputs, state)\n"
    "    route = interlocking.route_by_id(route_id)\n"
    "    return InterlockingResolution(\n"
    "        interlocking_id=interlocking.interlocking_id,\n"
    "        route_id=route.route_id,\n"
    "        train_id=route.train_id,\n"
    "        train_path=route.train_path,\n"
    "    )\n"
)


def test_function_based_station_master_wiring_is_followed() -> None:
    # atdd idiom: a concrete map handed to resolve_journey(...) is real wiring the matcher must read,
    # exactly as a game-app JOURNEY_MAP literal is. Both the bare and the Name-bound form resolve.
    inline = (
        "from atdd.runtime.interlocking import resolve_journey\n"
        "def dispatch(action, inputs):\n"
        "    return resolve_journey({\n"
        "        'start_match': '3001-solo',\n"
        "        'resolve_match': {'interlocking_id': 'interlocking:match-resolution',\n"
        "                          'path': 'plan/_trains/_interlockings/match-resolution.yaml'},\n"
        "    }, action)\n"
    )
    journey = detector.parse_journey_map(inline)
    assert journey["resolve_match"]["kind"] == "interlocking"
    assert journey["resolve_match"]["interlocking_id"] == "interlocking:match-resolution"
    assert journey["start_match"]["kind"] == "direct"

    name_bound = (
        "JOURNEY = {'resolve_match': {'interlocking_id': 'interlocking:match-resolution',\n"
        "                             'path': 'plan/_trains/_interlockings/match-resolution.yaml'}}\n"
        "def dispatch(action):\n"
        "    return resolve_journey(JOURNEY, action)\n"
    )
    assert detector.parse_journey_map(name_bound)["resolve_match"]["kind"] == "interlocking"


def test_station_master_definition_alone_yields_no_invented_wiring() -> None:
    # atdd's Station Master only DEFINES resolve_journey (map is a runtime parameter); there is no
    # call site handing it a concrete map. The matcher must NOT hallucinate wiring — it returns {} so
    # a genuinely unwired exposed interlocking still surfaces via declaration_to_station.
    assert "def resolve_journey" in _ATDD_STATION_MASTER  # guard: this IS the function-based idiom
    assert detector.parse_journey_map(_ATDD_STATION_MASTER) == {}


def test_variable_built_resolution_is_provenance_bound_not_undecidable() -> None:
    # atdd builds InterlockingResolution from `route = interlocking.route_by_id(...)` attributes.
    # runtime_resolution_literals sees NO literal route/train kwarg; provenance classifies
    # route.route_id / route.train_id as "bound" (derived from the loaded route space) — so
    # runtime_to_declaration holds by construction, WITHOUT a literal.
    assert detector.runtime_resolution_literals(_ATDD_RUNNER) == []  # no string-literal resolution kwargs
    prov = detector.runtime_resolution_provenance(_ATDD_RUNNER)
    kinds = {(kind, provenance) for kind, provenance, *_ in prov}
    assert ("route", "bound") in kinds
    assert ("train", "bound") in kinds
    assert all(provenance == "bound" for _kind, provenance, *_ in prov)  # nothing undecidable


def test_opaque_variable_resolution_is_surfaced_not_silently_passed() -> None:
    # A resolution built from an opaque variable (no route_by_id provenance) is UNDECIDABLE by static
    # scan. It must NOT be silently passed: provenance flags it, and runtime_to_declaration surfaces it.
    opaque = (
        "def resolve_train(self, action):\n"
        "    picked = external_pick(action)\n"
        "    return InterlockingResolution(route_id=picked.rid, train_id=picked.tid)\n"
    )
    prov = detector.runtime_resolution_provenance(opaque)
    assert {(kind, provenance) for kind, provenance, *_ in prov} == {
        ("route", "undecidable"),
        ("train", "undecidable"),
    }


def _write_atdd_shaped_repo(root: Path, runner_src: str, station_src: str) -> None:
    il_dir = root / "plan" / "_trains" / "_interlockings"
    il_dir.mkdir(parents=True)
    (root / "plan" / "_trains" / "3007-x.yaml").write_text("train_id: 3007-x\n", encoding="utf-8")
    (il_dir / "match-resolution.yaml").write_text(
        "interlocking_id: interlocking:match-resolution\n"
        "entrypoint:\n  exposed: true\n  actions:\n  - resolve_match\n"
        "routes:\n"
        "- route_id: nominal-all-voted\n  train_id: 3007-x\n"
        "  train_path: plan/_trains/3007-x.yaml\n",
        encoding="utf-8",
    )
    rt = root / "src" / "atdd" / "runtime" / "interlocking"
    rt.mkdir(parents=True)
    (rt / "runner.py").write_text(runner_src, encoding="utf-8")
    (rt / "station_master.py").write_text(station_src, encoding="utf-8")


_ATDD_LAYOUT = json.dumps(
    {
        "python_runtime": ["src/atdd/runtime/interlocking/*.py"],
        "station_master": ["src/atdd/runtime/interlocking/station_master.py"],
    }
)


def test_atdd_shaped_repo_reds_on_unwired_exposed_interlocking_only(tmp_path, monkeypatch) -> None:
    # END-TO-END dogfood shape: an exposed interlocking declared in YAML, atdd's runtime/station under
    # a src-style layout override. runtime_to_declaration must NOT fire (resolutions are
    # provenance-bound), but declaration_to_station MUST fire — the exposed interlocking has no Station
    # Master wiring (function-based Station Master with no concrete map). This is the genuine RED the
    # dogfood is meant to surface, not a matcher-blindness false positive.
    _write_atdd_shaped_repo(tmp_path, _ATDD_RUNNER, _ATDD_STATION_MASTER)
    monkeypatch.setenv(detector.ENV_LAYOUT, _ATDD_LAYOUT)
    v = detector.scan_root(tmp_path)
    _assert_v11_shape(v)
    dirs = _directions(v)
    assert detector.DIR_RUNTIME_DECL not in dirs, "resolutions are provenance-bound; must not RED"
    assert detector.DIR_DECL_STATION in dirs, "exposed interlocking is genuinely unwired — must RED"
    assert any("resolve_match" in item["evidence"] for item in v)


# ── 2. emission (writes the RAW report; does NOT decide disposition) ───────────


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
