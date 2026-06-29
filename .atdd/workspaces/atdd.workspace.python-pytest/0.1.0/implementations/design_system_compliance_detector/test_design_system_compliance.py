"""Runnable enforcement for the design-system-compliance rule family.

Two layers (mirrors composition_completeness_detector / structured_logging_detector):

  1. DETECTOR SELF-TESTS — pin the ported regex/scan logic: the clean design
     system emits nothing; the dirty fixture emits ALL SEVEN rule_ids, exactly
     once each (one file per rule, with deliberate overlaps kept distinct); the
     records are the full v1.1 shape.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan ``ATDD_SCAN_ROOTS``
     and write the RAW report to ``ATDD_VIOLATIONS_REPORT`` (§3).

All seven rule_ids are `strict`; aggregation is the consumer's job (§1). No core
(``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import design_system_compliance as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"

ALL_RULE_IDS = {
    detector.RULE_PRIMITIVES,
    detector.RULE_COLOR,
    detector.RULE_ORPHAN_EXPORT,
    detector.RULE_FOUNDATIONS,
    detector.RULE_HIERARCHY_IMPORT,
    detector.RULE_HARDCODED,
    detector.RULE_ORPHAN_UI,
}


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_clean_design_system_is_clean() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_dirty_emits_all_seven_rule_ids() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    assert {item["rule_id"] for item in v} == ALL_RULE_IDS


def test_dirty_emits_exactly_one_per_rule() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    counts: dict[str, int] = {}
    for item in v:
        counts[item["rule_id"]] = counts.get(item["rule_id"], 0) + 1
    assert counts == {rid: 1 for rid in ALL_RULE_IDS}


def test_presentation_without_ds_import_is_primitives_and_orphan_ui() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    by_rule = {x["rule_id"]: x for x in v}
    assert "MatchView.tsx" in by_rule[detector.RULE_PRIMITIVES]["file"]
    assert "MatchView.tsx" in by_rule[detector.RULE_ORPHAN_UI]["file"]


def test_primitive_into_components_is_hierarchy_break() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    hits = [x for x in v if x["rule_id"] == detector.RULE_HIERARCHY_IMPORT]
    assert len(hits) == 1
    assert "Box.tsx" in hits[0]["file"]
    assert "components" in hits[0]["evidence"]


def test_unconsumed_export_is_orphan_export() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    hits = [x for x in v if x["rule_id"] == detector.RULE_ORPHAN_EXPORT]
    assert len(hits) == 1
    assert "Orphan" in hits[0]["evidence"]


def test_raw_pixel_in_primitive_is_foundations_break() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    hits = [x for x in v if x["rule_id"] == detector.RULE_FOUNDATIONS]
    assert len(hits) == 1
    assert "Box.tsx" in hits[0]["file"]


def test_raw_color_and_hardcoded_spacing_are_token_violations() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    color = [x for x in v if x["rule_id"] == detector.RULE_COLOR]
    hard = [x for x in v if x["rule_id"] == detector.RULE_HARDCODED]
    assert len(color) == 1 and "#3a7bd5" in color[0]["evidence"]
    assert len(hard) == 1 and "16px" in hard[0]["evidence"]


def test_records_are_full_v1_1_shape() -> None:
    for item in detector.scan_root(_HERE / "fixtures" / "dirty"):
        assert set(item) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}
        assert isinstance(item["source_line"], str)
        assert item["line"] >= 1 and item["col"] >= 0


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


def test_emit_raw_design_system_report() -> None:
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
