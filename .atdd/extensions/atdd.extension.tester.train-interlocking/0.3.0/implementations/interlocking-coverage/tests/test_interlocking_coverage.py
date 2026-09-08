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
    train_id: 3007-match-resolution-standard
  - route_id: alternate-timeout
    category: alternate
    train_id: 3207-match-resolution-timeout
"""


def test_parse_interlocking_extracts_routes_and_entrypoint() -> None:
    rec = detector.parse_interlocking(_INTERLOCKING_YAML)
    assert rec is not None
    assert rec["interlocking_id"] == "interlocking:match-resolution"
    assert [r["route_id"] for r in rec["routes"]] == ["nominal-all-voted", "alternate-timeout"]
    assert rec["exposed"] is True
    assert rec["actions"] == ["resolve_match"]
    assert rec["routes"][0]["category"] == "nominal"


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
    # The digit is retired (#1421/#1440), so it is never itself reported missing —
    # but a LEGACY source asserting only route_category_digit must still be told it
    # is missing route_category, rather than silently passing on the dead field.
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
    assert "category 'alternate'" in item["evidence"]
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


# ── STAGED: train-sequence-is-exercised ───────────────────────────────────────


def test_asserts_a_sequence_requires_a_COMPARISON_not_a_mention() -> None:
    """The first cut counted a bare truthiness check as coverage.

    `assert trace["steps"]` mentions the word and proves nothing about the order —
    the same over-broad trigger that makes a bare `\\btrace\\b` drag unrelated tests
    into trace-binding. Caught by running the check against a real consumer.
    """
    assert detector.asserts_a_sequence('    assert trace["steps"] == declared') is True
    assert detector.asserts_a_sequence('    assert result.sequence == ["a", "b"]') is True
    assert detector.asserts_a_sequence('    assert trace["steps"]') is False
    assert detector.asserts_a_sequence('    steps = run()') is False


def test_trains_reachable_from_routes_follows_the_route_space() -> None:
    records = [{"routes": [{"train_id": "3007-x"}, {"train_id": "3207-y"}, {"train_id": None}]}]
    assert detector.trains_reachable_from_routes(records) == {"3007-x", "3207-y"}


def test_a_declared_train_with_no_sequence_assertion_is_reported() -> None:
    # The DIRTY fixture declares a wagon sequence for each train and asserts only
    # which train is selected. It used to point at `clean`, which stopped making
    # sense when the rule was gated: clean must now pass its own family, and a
    # train with no declared sequence is NOT_APPLICABLE rather than a violation.
    found = detector.scan_execution(_FIXTURES / "dirty_sequence_unasserted")
    assert found, "the dirty fixture declares sequences that no test asserts"
    assert all(v["rule_id"] == detector.RULE_SEQUENCE for v in found)
    assert any("wagon SEQUENCE" in v["evidence"] for v in found)


def test_node_status_agrees_with_what_the_gated_scan_emits() -> None:
    """The invariant that survives being enabled — see the coder sibling.

    Asserting the check STAYS unwired becomes the wrong test the moment someone
    wires it. This pins the relationship instead, so it needs no edit on the day
    the decision is made: draft must not be gated, active must be.
    """
    import yaml

    node = yaml.safe_load(
        (_HERE.parents[2] / "conventions" / f"{detector.RULE_SEQUENCE}.convention.yaml").read_text()
    )
    # A tree that TRIPS the rule: sequences declared, only selection asserted.
    # This was `clean`, which no longer trips it — clean must pass its own family
    # now that the rule is gated, and it declares no sequence to exercise.
    tree = _FIXTURES / "dirty_sequence_unasserted"
    staged = {v["rule_id"] for v in detector.scan_execution(tree)}
    gated = {v["rule_id"] for v in detector.scan_root(tree)}

    assert detector.RULE_SEQUENCE in staged, (
        "the validator must detect the violation regardless of whether it is gated"
    )
    if node["status"] == "active":
        assert detector.RULE_SEQUENCE in gated, (
            "an ACTIVE node claims live enforcement, so the gated scan must emit it"
        )
    else:
        assert detector.RULE_SEQUENCE not in gated, (
            f"node is {node['status']!r} but the gated scan emits it"
        )


def test_the_staged_node_is_bound_and_honestly_marked() -> None:
    """Same binding check as the coder sibling: emits is not realizes."""
    import yaml

    impl = yaml.safe_load((_HERE.parent / "atdd.implementation.yaml").read_text())
    realizes = impl["realizes_convention"]
    realizes = [realizes] if isinstance(realizes, str) else realizes
    assert detector.RULE_SEQUENCE in realizes, "node has no validator binding"
    assert detector.RULE_SEQUENCE in impl["emits_rule_ids"]

    node = yaml.safe_load(
        (_HERE.parents[2] / "conventions" / f"{detector.RULE_SEQUENCE}.convention.yaml").read_text()
    )
    assert node["metadata"]["disposition"] == "advisory"
    # Status deliberately not pinned — see the coder sibling. The status/gate
    # relationship is owned by the invariant test, which survives enablement.
    assert node["status"] in {"draft", "active", "deprecated"}
# ── the Station Master is STRUCTURE, not a name ───────────────────────────────


def test_a_module_style_station_master_is_silent() -> None:
    """Found by running the extension against a real consumer, not a fixture.

    The smoke check required a symbol literally named StationMaster. Nothing asks for
    that: coder.train.station-master-interlocking-routing defines the Station Master
    as python/app.py carrying a JOURNEY_MAP, and the CODER detector matches it that
    way. A consumer whose entrypoint was a module-level dispatch() passed the coder
    rule and failed this one, with no documented way to satisfy both — and the old
    pattern matched only because this package's own fixture exports a class with that
    name.
    """
    assert detector.scan_root(_FIXTURES / "clean_module_station_master") == []


def test_station_master_is_still_detected_by_the_class_name() -> None:
    """Widening the match must not have dropped the original form."""
    assert detector._STATION_MASTER.search("station_master = StationMaster()")
    assert detector._STATION_MASTER.search("import app")
    assert detector._STATION_MASTER.search("assert 'x' in app.JOURNEY_MAP")
    assert not detector._STATION_MASTER.search("a wholly unrelated sentence")


# ── trace fields must be ASSERTED, not merely mentioned ───────────────────────


def test_mentioning_every_field_without_asserting_them_is_reported() -> None:
    """The defect: a strict, severity-1, gate-blocking rule satisfied by a mention.

    The check searched the whole source for each field NAME, so a field in a dict
    literal counted as asserted. Found by running this package against a consumer
    repo it did not ship.
    """
    v = detector.scan_root(_FIXTURES / "dirty_trace_unasserted")
    assert _rule_ids(v) == {detector.RULE_TRACE}
    assert any("guard_id" in x["evidence"] for x in v)


def test_a_whole_mapping_assertion_is_accepted() -> None:
    """`assert trace == expected` asserts every field at once.

    Narrowing to per-field asserts without this escape would trade a real defect for
    a false positive against a legitimate test.
    """
    assert detector.unasserted_trace_fields(
        '    assert trace == expected\n'
    ) == []
    # ...but a per-field assert must NOT be read as a whole-mapping one. The first
    # cut allowed anything between the name and `==`, so every per-field assertion
    # switched the whole check off — a fix that disabled the rule it was fixing.
    partial = '    assert trace["route_id"] == "nominal-all-voted"\n'
    assert "guard_id" in detector.unasserted_trace_fields(partial)


def test_field_detection_stays_separable_from_assert_scoping() -> None:
    """Two concerns, two functions — conflating them broke a unit test of neither."""
    assert "route_category" in detector.missing_trace_fields('trace["route_category_digit"]')
    assert "route_category_digit" not in detector.missing_trace_fields('trace["route_category_digit"]')
    assert detector.asserted_text("x = 1\nassert y == 2\nz = 3") == "assert y == 2"
