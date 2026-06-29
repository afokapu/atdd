"""v1.1 structured-report emission for coder.logging.print.

ADDITIVE mechanical migration (PROVIDER-CONTRACT-v1.1.md §4): the Phase-0 print
impl is a v1.0.0 detector whose original enforcement (``test_logging_print.py``,
LEFT UNTOUCHED) reads ``$ATDD_SCAN_TARGET`` and asserts emptiness. That coarse
v1.0.0 path can only surface a single root-location violation via the exit-code
fallback and does not honor ``ATDD_SCAN_ROOTS``.

This sibling test wires the SAME detector (``logging_print.scan_path`` — no
detection re-implemented) to the v1.1 structured channel so the run adapter's
report path fires and a downstream consumer (ATDD core's ``disposition_gate``,
reached through the CW-Phase 0 provider CLI) receives per-site
``{rule_id, file, line, col, evidence, source_line}`` records (§3.2) instead of
the coarse v1.0.0 fallback.

Per §1 the provider emits RAW facts only: this test writes the report and
passes. It NEVER asserts ``violations == []`` — that would be the provider
silently applying ``strict``. The disposition verdict is the consumer's job.

NOTE: ``logging_print.scan_path`` has no ``ATDD_SCAN_EXCLUDES`` support (the
v1.0.0 detector predates it); excludes are accepted by the contract but ignored
by this print detector. The structured_logging detector is the exclude-aware
sibling. This is documented as a Phase-0 gap, not papered over here.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import logging_print as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


def _scan_roots() -> list[Path]:
    """Resolve the scan roots from ``ATDD_SCAN_ROOTS`` (JSON list), with the
    v1.0.0 single-root fallback then the default fixture, mirroring the
    structured_logging detector. Absolute paths verbatim; relative against the
    implementation dir (so the impl's own fixtures still work)."""
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


def _to_v11_record(root: Path, raw: dict) -> dict:
    """Adapt one ``logging_print.scan_path`` dict to a v1.1 violation record.

    ``scan_path`` emits ``{rule_id, location="<rel>:<line>:<col>", evidence}``.
    The v1.1 contract (§3.2) wants ``file``/``line``/``col`` decomposed plus the
    RAW ``source_line``. The detector's AST findings are reused verbatim; only
    the field shaping + source-line read are added here (contract glue).
    """
    rel, line_s, col_s = raw["location"].rsplit(":", 2)
    line, col = int(line_s), int(col_s)
    source_line = ""
    try:
        source_line = (root / rel).read_text(encoding="utf-8").splitlines()[line - 1]
    except (OSError, UnicodeDecodeError, IndexError):
        source_line = ""
    return {
        "rule_id": raw["rule_id"],
        "file": rel,
        "line": line,
        "col": col,
        "evidence": raw["evidence"],
        "source_line": source_line,
    }


def test_emit_raw_v11_report() -> None:
    """Scan ``ATDD_SCAN_ROOTS`` and write the RAW v1.1 report; do NOT decide."""
    roots = _scan_roots()
    violations: list[dict] = []
    for root in roots:
        for raw in detector.scan_path(root):  # reuse the REAL detector
            violations.append(_to_v11_record(root, raw))

    report_path = os.environ.get(ENV_REPORT)
    if report_path:
        Path(report_path).write_text(
            json.dumps(
                {
                    "contract_version": CONTRACT_VERSION,
                    "scan_roots": [str(r) for r in roots],
                    "violations": violations,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    # Run-health assertion only — emptiness is NOT gated here (§1).
    assert isinstance(violations, list)
