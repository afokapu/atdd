"""Runnable enforcement for tester.acceptance-violation.live-smoke-acceptance-must-execute.

Two layers:

  1. DETECTOR SELF-TESTS — pin the ported logic (self-skip mechanisms matched,
     live_smoke header gate, runs-or-fails test clean, the non-live_smoke control
     is NOT flagged). Always green: they prove the detector is healthy.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan ``ATDD_SCAN_ROOTS``
     (with ``ATDD_SCAN_EXCLUDES``) and write the RAW structured violations to
     ``ATDD_VIOLATIONS_REPORT`` for ``run.py`` to read back.

``tester.acceptance-violation.live-smoke-acceptance-must-execute`` is ``strict``;
the detector still only EMITS the RAW self-skip list. The strict verdict (any
self-skip -> FAIL) is the downstream consumer's disposition decision, never the
detector's. The test asserts run-health, not emptiness.

No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import live_smoke_execution as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_self_skip_mechanisms_are_matched() -> None:
    cases = [
        "    pytest.skip('x')",
        "    pytest.importorskip('mod')",
        "@pytest.mark.skipif(cond)",
        "@pytest.mark.skip",
        "    if not live_smoke_available():",
    ]
    for src in cases:
        assert detector.detect_self_skip(src) is not None, src


def test_runs_or_fails_source_has_no_self_skip() -> None:
    src = "def test_x():\n    gateway.charge('a', 1)\n    assert True\n"
    assert detector.detect_self_skip(src) is None


def test_live_smoke_header_gate() -> None:
    assert detector.is_live_smoke_test("# execution_kind: live_smoke\nx = 1\n") is True
    assert detector.is_live_smoke_test("#  execution_kind:live_smoke\n") is True
    assert detector.is_live_smoke_test("# Phase: SMOKE\nx = 1\n") is False
    assert detector.is_live_smoke_test("x = 1\n") is False


def test_detect_self_skip_reports_line_and_col() -> None:
    src = "line one\nline two\n    pytest.skip('boom')\n"
    hit = detector.detect_self_skip(src)
    assert hit is not None
    lineno, col, label = hit
    assert lineno == 3
    assert col == 4  # 0-based column of `pytest.skip`
    assert label == "pytest.skip(...)"


def test_clean_fixture_has_no_self_skip() -> None:
    assert detector.scan_root(_HERE / "fixtures" / "clean") == []


def test_dirty_fixture_flags_only_the_live_smoke_self_skip() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    # Exactly one violation: the live_smoke test that self-skips. The unit-test
    # control (skipif, no live_smoke header) is correctly NOT flagged.
    assert len(v) == 1, f"expected 1 raw self-skip, got {len(v)}: {[i['file'] for i in v]}"
    item = v[0]
    assert item["file"] == "test_inventory_live_smoke.py"
    assert item["rule_id"] == detector.RULE_LIVE_SMOKE_MUST_EXECUTE
    assert item["line"] >= 1 and item["col"] >= 0
    assert set(item) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}
    assert "pytest.skip" in item["source_line"]


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


def test_emit_raw_live_smoke_report() -> None:
    """Scan the supplied roots and emit the RAW violation report (NOT a verdict)."""
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
