"""Runnable enforcement for coder.refactor.nplus1 under python-pytest.

Two layers: detector self-tests (DB call in a loop is flagged; DB call outside a
loop is clean; non-DB call ignored; the ``# noqa: N+1`` detection-exemption is
honored), then EMISSION of the RAW report to ``ATDD_VIOLATIONS_REPORT``.

``coder.refactor.nplus1`` is ``strict``; the strict verdict is the downstream
consumer's job. The test asserts run-health, not emptiness.

No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import query_count as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_db_call_in_for_loop_is_detected() -> None:
    src = "def f(ids, repo):\n    for i in ids:\n        repo.find_one(i)\n"
    hits = detector.detect_n_plus_one(src)
    assert len(hits) == 1
    assert ".find_one()" in hits[0][2]
    assert "For" in hits[0][2]


def test_db_call_in_comprehension_is_detected() -> None:
    src = "def f(ids, repo):\n    return [repo.fetchone(i) for i in ids]\n"
    hits = detector.detect_n_plus_one(src)
    assert len(hits) == 1
    assert "ListComp" in hits[0][2]


def test_db_call_outside_loop_is_clean() -> None:
    src = "def f(repo):\n    return repo.find_many()\n"
    assert detector.detect_n_plus_one(src) == []


def test_non_db_call_in_loop_is_ignored() -> None:
    src = "def f(items):\n    for x in items:\n        print(x)\n"
    assert detector.detect_n_plus_one(src) == []


def test_noqa_marker_is_a_detection_exemption() -> None:
    # `# noqa: N+1` drops the call before it becomes a violation (core parity).
    src = "def f(ids, repo):\n    for i in ids:\n        repo.find_one(i)  # noqa: N+1\n"
    assert detector.detect_n_plus_one(src) == []


def test_scan_emits_full_v11_shape_with_source_line() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    assert v, "dirty fixture must emit at least one violation"
    for item in v:
        assert set(item) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}
        assert item["rule_id"] == detector.RULE_NPLUS1
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
        single = os.environ.get("ATDD_SCAN_TARGET", "fixtures/clean")
        names = [single]
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


def test_emit_raw_query_count_report() -> None:
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
