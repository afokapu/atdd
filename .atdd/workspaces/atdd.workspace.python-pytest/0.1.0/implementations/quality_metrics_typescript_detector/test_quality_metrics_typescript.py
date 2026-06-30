"""Runnable enforcement for the coder REFACTOR-phase TS quality metrics.

Two layers (mirrors composition_completeness_detector):

  1. DETECTOR SELF-TESTS — pin the ported regex metrics: the clean fixture emits
     nothing; the dirty fixture emits BOTH rule_ids (low-MI file + uncommented
     file); records are full v1.1 shape. Both rules are PURE STDLIB (regex MI —
     no radon), so both fire deterministically.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan ``ATDD_SCAN_ROOTS``
     and write the RAW report to ``ATDD_VIOLATIONS_REPORT`` (§3).

Both rule_ids are `strict`; aggregation is the consumer's job (§1). No core
(``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quality_metrics_typescript as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_clean_fixture_is_clean() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_dirty_fixture_emits_both_rule_ids() -> None:
    rule_ids = {v["rule_id"] for v in detector.scan_root(_HERE / "fixtures" / "dirty")}
    assert detector.RULE_MI_TS in rule_ids
    assert detector.RULE_COMMENTS_TS in rule_ids


def test_mi_rule_flags_the_low_mi_file() -> None:
    hits = [v for v in detector.scan_root(_HERE / "fixtures" / "dirty")
            if v["rule_id"] == detector.RULE_MI_TS]
    assert any("lowMi.ts" in v["file"] for v in hits)


def test_comments_rule_flags_the_uncommented_file() -> None:
    hits = [v for v in detector.scan_root(_HERE / "fixtures" / "dirty")
            if v["rule_id"] == detector.RULE_COMMENTS_TS]
    assert any("Uncommented.tsx" in v["file"] for v in hits)


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


def test_emit_raw_quality_report_typescript() -> None:
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
