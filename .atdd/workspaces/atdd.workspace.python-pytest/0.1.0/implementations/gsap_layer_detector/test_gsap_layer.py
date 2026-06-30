"""Runnable enforcement for coder.presentation.gsap-layer under python-pytest.

Two layers (mirrors structured_logging_detector):

  1. DETECTOR SELF-TESTS — pin the ported regex/layer logic (GSAP found in
     application -> RULE_LAYER; GSAP in commons -> RULE_COMMONS; GSAP in
     presentation -> clean; non-GSAP import ignored).

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan the explicit
     ``ATDD_SCAN_ROOTS`` (with ``ATDD_SCAN_EXCLUDES``) and write the RAW
     structured violations to ``ATDD_VIOLATIONS_REPORT`` for ``run.py`` (§3).

Both rule_ids are `strict`, so emptiness IS the eventual verdict downstream — but
the detector still does NOT ``assert violations == []`` itself; the strict
aggregation is the consumer's job (§1). The pytest exit code is run-health only.

No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gsap_layer as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_gsap_in_application_is_layer_violation() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    layer_hits = [x for x in v if x["rule_id"] == detector.RULE_LAYER]
    assert layer_hits, "expected a gsap-layer violation in the dirty fixture"
    assert all("gsap" in x["source_line"].lower() for x in layer_hits)


def test_gsap_in_commons_is_commons_violation() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    assert any(x["rule_id"] == detector.RULE_COMMONS for x in v)


def test_gsap_in_presentation_is_clean() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_presentation_layer_predicate() -> None:
    assert detector.is_presentation_layer(("arena", "show", "presentation", "X.tsx")) is True
    assert detector.is_presentation_layer(("arena", "show", "application", "x.ts")) is False
    assert detector.is_presentation_layer(("commons", "anim", "presentation", "x.ts")) is False


def test_non_gsap_import_is_ignored() -> None:
    assert detector.find_gsap_import('import { useState } from "react"\n') is None


def test_scan_emits_both_rule_ids_with_source_line() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    rule_ids = {item["rule_id"] for item in v}
    assert detector.RULE_LAYER in rule_ids
    assert detector.RULE_COMMONS in rule_ids
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


def test_emit_raw_gsap_report() -> None:
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
