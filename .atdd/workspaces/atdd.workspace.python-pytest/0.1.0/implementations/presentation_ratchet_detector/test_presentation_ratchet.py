"""Runnable enforcement for coder.refactor.coach-ratchet-pres.

Two layers (mirrors structured_logging_detector):

  1. DETECTOR SELF-TESTS — pin the ported pure predicate (25% reduction flagged;
     exactly-20% allowed; full deletion = 100%; non-presentation ignored; growth
     ignored) and the manifest reader.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — read the mounted
     ``reductions.json`` under ``ATDD_SCAN_ROOTS`` and write the RAW report to
     ``ATDD_VIOLATIONS_REPORT`` (§3).

CRITICAL — this detector emits the RAW reduction even when smoke evidence exists
(the ``evidenced`` fixture). The smoke-evidence GATE (advisory disposition) is the
downstream consumer's call, NOT the detector's — exactly the suppress-and-clean
separation, with smoke evidence in the marker's role. So no ``assert violations ==
[]`` here. No core (``atdd.coach.*``) imports.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import presentation_ratchet as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_25pct_presentation_reduction_is_flagged() -> None:
    diffs = [("web/src/match/presentation/MatchPage.tsx", 200, 150, 358)]
    out = detector.detect_presentation_reductions(diffs)
    assert len(out) == 1
    assert abs(out[0]["reduction_ratio"] - 0.25) < 1e-9


def test_exactly_20pct_is_allowed() -> None:
    diffs = [("web/src/match/presentation/Page.tsx", 100, 80, 1)]
    assert detector.detect_presentation_reductions(diffs) == []


def test_full_deletion_is_100pct() -> None:
    diffs = [("python/auth/presentation/login.py", 80, 0, 1)]
    out = detector.detect_presentation_reductions(diffs)
    assert len(out) == 1
    assert abs(out[0]["reduction_ratio"] - 1.0) < 1e-9


def test_non_presentation_and_growth_ignored() -> None:
    diffs = [
        ("python/auth/domain/user.py", 200, 50, 1),     # not presentation
        ("web/src/match/presentation/Grew.tsx", 100, 200, 1),  # grew
        ("web/src/match/presentation/New.tsx", 0, 50, 1),      # new file
    ]
    assert detector.detect_presentation_reductions(diffs) == []


def test_dirty_manifest_emits_one_violation() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    assert len(v) == 1
    assert v[0]["rule_id"] == detector.RULE_RATCHET_PRES
    assert v[0]["issue"] == 358


def test_evidenced_manifest_still_emits_raw() -> None:
    # The detector NEVER reads smoke evidence: the evidenced fixture (same
    # reduction, evidence present) still yields a NON-EMPTY raw list. The flip to
    # PASS happens entirely in the consumer.
    v = detector.scan_root(_HERE / "fixtures" / "evidenced")
    assert len(v) == 1


def test_clean_manifest_emits_nothing() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_records_are_full_v1_1_shape() -> None:
    for item in detector.scan_root(_HERE / "fixtures" / "dirty"):
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


def test_emit_raw_ratchet_report() -> None:
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

    assert isinstance(violations, list)
