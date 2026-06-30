"""Runnable enforcement for coder.security.sql-injection/-missing-auth/-hardcoded-secret.

Two layers (mirrors composition_completeness_detector):

  1. DETECTOR SELF-TESTS — pin the ported AST/regex logic: the clean fixture emits
     nothing; the dirty fixture emits ALL THREE rule_ids; the concatenated SQL is a
     sql-injection site, the un-Depends route is a missing-auth site, and the two
     secret literals are two hardcoded-secret sites.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan ``ATDD_SCAN_ROOTS`` and
     write the RAW report to ``ATDD_VIOLATIONS_REPORT`` (§3).

All three rule_ids are `strict`; the strict aggregation is the consumer's job (§1).
No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import security_patterns as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_clean_emits_nothing() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_dirty_emits_all_three_rule_ids() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    rule_ids = {item["rule_id"] for item in v}
    assert rule_ids == {detector.RULE_SQL, detector.RULE_AUTH, detector.RULE_SECRET}


def test_dirty_sql_injection_site() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    sql_hits = [x for x in v if x["rule_id"] == detector.RULE_SQL]
    assert len(sql_hits) == 1
    assert "bad_db.py" in sql_hits[0]["file"]
    assert "SELECT" in sql_hits[0]["source_line"]


def test_dirty_missing_auth_site() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    auth_hits = [x for x in v if x["rule_id"] == detector.RULE_AUTH]
    assert len(auth_hits) == 1
    assert "bad_routes.py" in auth_hits[0]["file"]
    assert "admin_panel" in auth_hits[0]["evidence"]


def test_dirty_two_secret_sites() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    secret_hits = [x for x in v if x["rule_id"] == detector.RULE_SECRET]
    assert len(secret_hits) == 2
    names = {h["file"] for h in secret_hits}
    assert names == {"bad_config.py"}


def test_dirty_total_is_four_raw() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    assert len(v) == 4  # 1 sql + 1 auth + 2 secret


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


def test_emit_raw_security_report() -> None:
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
