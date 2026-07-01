"""Runnable enforcement for coder.boundaries.xlang-entity/-enum/-naming/-contract.

Two layers (mirrors composition_completeness_detector):

  1. DETECTOR SELF-TESTS — pin the ported extraction/comparison logic: the clean
     fixture (full cross-stack parity) emits nothing; the dirty fixture emits ALL
     FOUR rule_ids — Score implemented in Python only (entity), StatusEnum members
     differing across stacks (enum), Player spelled PlayerEntity vs PlayerModel
     (naming), and Trophy implemented nowhere (contract, plus entity).

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan ``ATDD_SCAN_ROOTS`` and
     write the RAW report to ``ATDD_VIOLATIONS_REPORT`` (§3).

MIXED disposition (applied downstream, §1): entity + contract are `advisory`
(synthetic, markerless aggregate locations); enum + naming are `strict`. The
detector emits all four RAW; the verdict is the consumer's job.
No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cross_language_consistency as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_clean_emits_nothing() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_dirty_emits_all_four_rule_ids() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    rule_ids = {item["rule_id"] for item in v}
    assert rule_ids == {
        detector.RULE_ENTITY,
        detector.RULE_ENUM,
        detector.RULE_NAMING,
        detector.RULE_CONTRACT,
    }


def test_dirty_entity_flags_score_and_trophy() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    entity_hits = {x["file"] for x in v if x["rule_id"] == detector.RULE_ENTITY}
    assert entity_hits == {"contracts/score", "contracts/trophy"}


def test_dirty_enum_flags_status_enum() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    enum_hits = [x for x in v if x["rule_id"] == detector.RULE_ENUM]
    assert len(enum_hits) == 1
    assert enum_hits[0]["file"] == "enums/StatusEnum"
    assert "pending" in enum_hits[0]["evidence"]


def test_dirty_naming_flags_player_suffix_drift() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    naming_hits = [x for x in v if x["rule_id"] == detector.RULE_NAMING]
    assert len(naming_hits) == 1
    assert naming_hits[0]["file"] == "naming/Player"
    assert "Entity" in naming_hits[0]["evidence"] and "Model" in naming_hits[0]["evidence"]


def test_dirty_contract_flags_unimplemented_trophy() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    contract_hits = [x for x in v if x["rule_id"] == detector.RULE_CONTRACT]
    assert len(contract_hits) == 1
    assert contract_hits[0]["file"] == "contracts/trophy"


def test_dirty_total_is_five_raw() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    assert len(v) == 5  # 2 entity + 1 enum + 1 naming + 1 contract


def test_records_are_full_v1_1_shape_with_synthetic_locations() -> None:
    for item in detector.scan_root(_HERE / "fixtures" / "dirty"):
        assert set(item) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}
        # Aggregate cross-file facts: synthetic location, no per-site source line.
        assert item["line"] == 1 and item["col"] == 0
        assert item["source_line"] == ""


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


def test_emit_raw_cross_language_report() -> None:
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
