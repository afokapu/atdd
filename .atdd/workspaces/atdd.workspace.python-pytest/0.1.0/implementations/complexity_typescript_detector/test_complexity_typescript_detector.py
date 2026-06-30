"""Runnable enforcement for coder.refactor.complexity-*-typescript (THREE rule_ids).

Two layers (mirrors composition_completeness_detector / gsap_layer_detector):

  1. DETECTOR SELF-TESTS — pin the ported regex/brace metric logic: the clean
     fixture emits nothing; the dirty fixture emits ALL THREE rule_ids; each
     metric trips on its dedicated function; every record is the full v1.1 shape.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan ``ATDD_SCAN_ROOTS``
     (with ``ATDD_SCAN_EXCLUDES``) and write the RAW report to
     ``ATDD_VIOLATIONS_REPORT`` (§3).

All three rule_ids are `strict`; the strict aggregation is the consumer's job
(§1). No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import complexity_typescript as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"

ALL_RULE_IDS = {
    detector.RULE_CYCLO_TS,
    detector.RULE_NEST_TS,
    detector.RULE_LEN_TS,
}


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_clean_fixture_is_clean() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_dirty_fixture_emits_all_three_rule_ids() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    assert {item["rule_id"] for item in v} == ALL_RULE_IDS


def test_cyclomatic_trips_on_its_function() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    hits = [x for x in v if x["rule_id"] == detector.RULE_CYCLO_TS]
    assert any("classify" in x["evidence"] for x in hits)


def test_nesting_trips_on_its_function() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    hits = [x for x in v if x["rule_id"] == detector.RULE_NEST_TS]
    assert any("deepNest" in x["evidence"] for x in hits)


def test_length_trips_on_its_function() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    hits = [x for x in v if x["rule_id"] == detector.RULE_LEN_TS]
    assert any("longFn" in x["evidence"] for x in hits)


def test_records_are_full_v1_1_shape() -> None:
    for item in detector.scan_root(_HERE / "fixtures" / "dirty"):
        assert set(item) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}
        assert isinstance(item["source_line"], str)
        assert item["line"] >= 1
        assert item["col"] == 0


def test_exclude_globs_drop_a_file() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty", exclude_globs=["complex.ts"])
    assert v == []


# ── 2. emission (writes the RAW report; does NOT decide disposition) ───────────


def _scan_roots() -> list[Path]:
    raw = os.environ.get(ENV_SCAN_ROOTS)
    if raw:
        try:
            names = json.loads(raw)
        except json.JSONDecodeError:
            names = []
    else:
        names = [os.environ.get("ATDD_SCAN_TARGET", "fixtures/clean")]
    roots: list[Path] = []
    for n in names:
        p = Path(n)
        roots.append(p if p.is_absolute() else (_HERE / p))
    return roots


def _exclude_globs() -> list[str]:
    raw = os.environ.get(ENV_SCAN_EXCLUDES)
    if not raw:
        return []
    try:
        globs = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(g) for g in globs] if isinstance(globs, list) else []


def test_emit_raw_complexity_typescript_report() -> None:
    roots = _scan_roots()
    violations = detector.scan_roots(roots, _exclude_globs())

    report_path = os.environ.get(ENV_REPORT)
    if report_path:
        payload = {
            "contract_version": CONTRACT_VERSION,
            "scan_roots": [str(r) for r in roots],
            "violations": violations,
        }
        Path(report_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    assert isinstance(violations, list)
