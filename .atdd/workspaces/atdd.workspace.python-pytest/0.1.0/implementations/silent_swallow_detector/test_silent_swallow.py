"""Runnable enforcement for coder.logging.coach-silent-swallow under python-pytest.

Two layers, exactly as the structured-logging re-proof:

  1. DETECTOR SELF-TESTS — pin the ported AST logic (swallow found, log/raise
     exempt, bare-pass found, non-return-non-pass ignored, exclusions). Always
     green: they prove the detector is healthy.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan ``ATDD_SCAN_ROOTS``
     (with ``ATDD_SCAN_EXCLUDES``) and write the RAW structured violations to
     ``ATDD_VIOLATIONS_REPORT`` for ``run.py`` to read back.

CRITICAL — this enforcement does NOT ``assert violations == []``.
``coder.logging.coach-silent-swallow`` is ``suppress-and-clean``; whether a
``# atdd:suppress(...)`` marker absorbs a raw violation is the DOWNSTREAM
CONSUMER's disposition decision (§1), never the detector's. The detector emits
the RAW list — INCLUDING marked handlers — and the test passes once it emits.

No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import silent_swallow as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_returning_swallow_is_detected() -> None:
    src = "try:\n    x()\nexcept Exception:\n    return None\n"
    hits = detector.detect_silent_swallows(src)
    assert len(hits) == 1


def test_bare_pass_swallow_is_detected() -> None:
    src = "try:\n    x()\nexcept Exception:\n    pass\n"
    hits = detector.detect_silent_swallows(src)
    assert len(hits) == 1
    assert "pass" in hits[0][2]


def test_handler_with_log_is_clean() -> None:
    src = "try:\n    x()\nexcept Exception:\n    logger.warning('boom')\n    return None\n"
    assert detector.detect_silent_swallows(src) == []


def test_handler_with_raise_is_clean() -> None:
    src = "try:\n    x()\nexcept Exception:\n    raise\n"
    assert detector.detect_silent_swallows(src) == []


def test_handler_without_return_or_pass_is_ignored() -> None:
    # State bookkeeping that lets execution continue is NOT flagged (core parity).
    src = "try:\n    x()\nexcept Exception:\n    counter = 1\n"
    assert detector.detect_silent_swallows(src) == []


def test_marked_handler_is_STILL_emitted_raw() -> None:
    # The detector emits even suppress-marked handlers; absorbing is the consumer's job.
    src = (
        "try:\n    x()\n"
        "except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow)\n"
        "    return None\n"
    )
    assert len(detector.detect_silent_swallows(src)) == 1


def test_test_and_init_files_are_excluded() -> None:
    assert detector.is_excluded(Path("pkg/test_x.py")) is True
    assert detector.is_excluded(Path("pkg/tests/h.py")) is True
    assert detector.is_excluded(Path("pkg/__init__.py")) is True
    assert detector.is_excluded(Path("pkg/conftest.py")) is True
    assert detector.is_excluded(Path("pkg/service.py")) is False


def test_scan_emits_full_v11_shape_with_source_line() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    assert v, "dirty fixture must emit at least one violation"
    for item in v:
        assert set(item) >= {"rule_id", "file", "line", "col", "evidence", "source_line"}
        assert item["rule_id"] == detector.RULE_SILENT_SWALLOW
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


def test_emit_raw_silent_swallow_report() -> None:
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

    # Run-health only: deliberately NOT gated on emptiness.
    assert isinstance(violations, list)
