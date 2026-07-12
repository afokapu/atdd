"""Runnable enforcement for the coder REFACTOR-phase quality metrics (python).

Two layers (mirrors composition_completeness_detector):

  1. DETECTOR SELF-TESTS — pin the ported detection: the clean fixture emits
     nothing; the dirty fixture emits the four pure-stdlib rule_ids
     (comments / duplication / naming / file-length); records are full v1.1 shape.
     The MI rule is radon-coupled: asserted present iff radon is importable,
     asserted ABSENT otherwise (the faithful 100.0-fallback behavior).

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan ``ATDD_SCAN_ROOTS``
     and write the RAW report to ``ATDD_VIOLATIONS_REPORT`` (§3).

All five rule_ids are `strict`; aggregation is the consumer's job (§1). No core
(``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quality_metrics as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"

# The four rule_ids that fire deterministically (pure stdlib, no radon).
STDLIB_RULES = {
    detector.RULE_COMMENTS,
    detector.RULE_DUP,
    detector.RULE_NAMING,
    detector.RULE_FILE_LEN,
}


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_clean_fixture_is_clean() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_dirty_fixture_emits_all_stdlib_rule_ids() -> None:
    rule_ids = {v["rule_id"] for v in detector.scan_root(_HERE / "fixtures" / "dirty")}
    assert STDLIB_RULES <= rule_ids, f"missing {STDLIB_RULES - rule_ids}"


def test_mi_leg_matches_radon_availability() -> None:
    rule_ids = {v["rule_id"] for v in detector.scan_root(_HERE / "fixtures" / "dirty")}
    if detector.radon_available():
        # radon present -> the low-MI fixture file must surface the MI rule.
        assert detector.RULE_MI in rule_ids
    else:
        # radon absent -> faithful 100.0 fallback -> MI never fires.
        assert detector.RULE_MI not in rule_ids


def test_comments_rule_targets_the_uncommented_file() -> None:
    hits = [v for v in detector.scan_root(_HERE / "fixtures" / "dirty")
            if v["rule_id"] == detector.RULE_COMMENTS]
    assert any("uncommented.py" in v["file"] for v in hits)


def test_duplication_rule_pairs_two_different_files() -> None:
    hits = [v for v in detector.scan_root(_HERE / "fixtures" / "dirty")
            if v["rule_id"] == detector.RULE_DUP]
    assert hits
    # evidence names file_a <-> file_b — two DIFFERENT files.
    assert any("dup_a.py" in v["evidence"] and "dup_b.py" in v["evidence"] for v in hits)


def test_naming_rule_flags_class_and_constant() -> None:
    hits = [v for v in detector.scan_root(_HERE / "fixtures" / "dirty")
            if v["rule_id"] == detector.RULE_NAMING]
    details = " | ".join(v["evidence"] for v in hits)
    assert "PascalCase" in details
    assert "UPPER_CASE" in details


def test_file_length_rule_flags_the_long_file() -> None:
    hits = [v for v in detector.scan_root(_HERE / "fixtures" / "dirty")
            if v["rule_id"] == detector.RULE_FILE_LEN]
    assert any("long_file.py" in v["file"] for v in hits)


def test_records_are_full_v1_1_shape() -> None:
    for item in detector.scan_root(_HERE / "fixtures" / "dirty"):
        assert set(item) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}
        assert isinstance(item["source_line"], str)
        assert item["line"] >= 1
        assert item["col"] >= 0


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


def test_emit_raw_quality_report() -> None:
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
