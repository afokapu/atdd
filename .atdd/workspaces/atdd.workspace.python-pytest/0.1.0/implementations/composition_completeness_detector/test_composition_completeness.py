"""Runnable enforcement for coder.refactor.composition-consumer/-root.

Two layers (mirrors structured_logging_detector):

  1. DETECTOR SELF-TESTS — pin the ported graph logic: the complete feature emits
     nothing; the dirty feature emits BOTH rule_ids; an unwired application file
     is a consumer violation; a composition.py that imports setters but never
     CALLS them fails to reach presentation (root violation) — the #955
     setter-wiring behavior.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan ``ATDD_SCAN_ROOTS``
     and write the RAW report to ``ATDD_VIOLATIONS_REPORT`` (§3).

Both rule_ids are `strict`; the strict aggregation is the consumer's job (§1).
No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import composition_completeness as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_complete_feature_is_clean() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_dirty_feature_emits_both_rule_ids() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    rule_ids = {item["rule_id"] for item in v}
    assert detector.RULE_CONSUMER in rule_ids
    assert detector.RULE_ROOT in rule_ids


def test_unwired_application_file_is_a_consumer_violation() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    consumer_hits = [x for x in v if x["rule_id"] == detector.RULE_CONSUMER]
    assert any("orphan_use_case.py" in x["file"] for x in consumer_hits)


def test_uncalled_setter_leaves_presentation_unreached() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    root_hits = [x for x in v if x["rule_id"] == detector.RULE_ROOT]
    assert len(root_hits) == 1
    assert "missing_presentation" in root_hits[0]["evidence"]


def test_detect_layer_classifies_composition_and_layers() -> None:
    assert detector.detect_layer(Path("f/composition.py")) == "composition"
    assert detector.detect_layer(Path("f/src/domain/x.py")) == "domain"
    assert detector.detect_layer(Path("f/src/presentation/c/x.py")) == "presentation"


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


def _exclude_globs() -> list[str]:
    raw = os.environ.get(ENV_SCAN_EXCLUDES)
    if not raw:
        return []
    try:
        globs = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(g) for g in globs] if isinstance(globs, list) else []


def test_emit_raw_composition_report() -> None:
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
