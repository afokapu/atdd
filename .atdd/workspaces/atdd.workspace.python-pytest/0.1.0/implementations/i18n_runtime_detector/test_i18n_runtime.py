"""Runnable enforcement for coder.presentation.i18n-config/-switcher.

Two layers (mirrors structured_logging_detector):

  1. DETECTOR SELF-TESTS — pin the ported regex logic (hardcoded array flagged;
     manifest/shared reference absolves; both rule_ids emitted from the dirty
     fixture; clean fixture emits nothing).

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan ``ATDD_SCAN_ROOTS``
     and write the RAW report to ``ATDD_VIOLATIONS_REPORT`` (§3).

Both rule_ids are `strict`; the strict aggregation is the consumer's job (§1).
The detector never asserts emptiness. No core (``atdd.coach.*``) imports.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import i18n_runtime as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_dirty_config_is_flagged() -> None:
    v = detector.scan_i18n_config(_HERE / "fixtures" / "dirty")
    assert len(v) == 1
    assert v[0]["rule_id"] == detector.RULE_CONFIG


def test_dirty_switcher_is_flagged() -> None:
    v = detector.scan_language_switcher(_HERE / "fixtures" / "dirty")
    assert len(v) == 1
    assert v[0]["rule_id"] == detector.RULE_SWITCHER


def test_clean_root_emits_nothing() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_manifest_reference_absolves_config() -> None:
    # A hardcoded array is fine if the file ALSO imports the manifest.
    assert detector.CONFIG_HARDCODED.search("const locales = ['en','fr']")
    assert any(
        re.search(p, "import { SUPPORTED_LOCALES } from './manifest'", re.IGNORECASE)
        for p in detector.CONFIG_MANIFEST_PATTERNS
    )


def test_scan_emits_both_rule_ids_with_source_line() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    rule_ids = {item["rule_id"] for item in v}
    assert detector.RULE_CONFIG in rule_ids
    assert detector.RULE_SWITCHER in rule_ids
    for item in v:
        assert set(item) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}
        assert isinstance(item["source_line"], str)


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


def test_emit_raw_i18n_report() -> None:
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
