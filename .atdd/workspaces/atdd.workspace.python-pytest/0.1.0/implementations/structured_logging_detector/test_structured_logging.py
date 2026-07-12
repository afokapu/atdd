"""Runnable enforcement for coder.logging.structured under the python-pytest provider.

This file is what the provider's ``pytest`` command collects. Two layers:

  1. DETECTOR SELF-TESTS — pin the ported AST logic (bare-log found, extra= clean,
     non-logger receiver ignored, print found, exclusions). Always green: they
     prove the detector itself is healthy.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan the explicit
     ``ATDD_SCAN_ROOTS`` (with ``ATDD_SCAN_EXCLUDES``) and write the RAW
     structured violations to ``ATDD_VIOLATIONS_REPORT`` for ``run.py`` to read
     back (PROVIDER-CONTRACT-v1.1.md §3).

CRITICAL — this enforcement does NOT ``assert violations == []``. ``coder.logging
.structured`` is ``suppress-and-clean``; deciding which raw violations are
absorbed by ``# atdd:suppress(...)`` markers is the DOWNSTREAM CONSUMER's
disposition decision (§1), never the workspace detector's. The detector emits the
RAW list — INCLUDING marked bare calls — and the test passes once it has emitted.
The pytest exit code is run-health, not a disposition verdict.

No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import structured_logging as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_bare_log_call_is_detected() -> None:
    hits = detector.detect_bare_log_calls('logger.info("hi")\n')
    assert len(hits) == 1
    assert hits[0][2] == "info"


def test_log_call_with_extra_is_clean() -> None:
    assert detector.detect_bare_log_calls('logger.info("hi", extra={"k": 1})\n') == []


def test_non_logger_receiver_is_ignored() -> None:
    # st.info(...) is a Streamlit call, not a logger — must not be flagged.
    assert detector.detect_bare_log_calls('st.info("hi")\n') == []


def test_print_call_is_detected() -> None:
    hits = detector.detect_print_calls('print("x")\n')
    assert len(hits) == 1


def test_test_and_init_files_are_excluded() -> None:
    assert detector.is_excluded(Path("pkg/test_x.py")) is True
    assert detector.is_excluded(Path("pkg/tests/h.py")) is True
    assert detector.is_excluded(Path("pkg/__init__.py")) is True
    assert detector.is_excluded(Path("pkg/service.py")) is False


def test_scan_emits_both_rule_ids_with_source_line() -> None:
    """One scan of the dirty fixture emits BOTH rule_ids, each with source_line."""
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    rule_ids = {item["rule_id"] for item in v}
    assert detector.RULE_PRINT in rule_ids
    assert detector.RULE_STRUCTURED in rule_ids
    # every record is the full v1.1 shape, including the RAW offending line
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
        # Legacy single-root fallback, then default fixture.
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


def test_emit_raw_structured_report() -> None:
    """Scan the supplied roots and emit the RAW violation report.

    NOT a disposition verdict — no ``assert violations == []``. The report is the
    v1.1 channel ``run.py`` reads; the suppress-and-clean / strict decision is
    made downstream by the consumer.
    """
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

    # Run-health assertion only: the scan completed and produced a well-formed
    # list. This deliberately does NOT gate on emptiness (that would be the
    # provider silently applying `strict`).
    assert isinstance(violations, list)
