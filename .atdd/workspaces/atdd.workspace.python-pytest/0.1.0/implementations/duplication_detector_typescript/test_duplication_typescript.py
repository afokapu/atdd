"""Runnable enforcement for coder.duplication.no-intra-layer-code-typescript.

What the provider's ``pytest`` command collects. Two layers:

  1. DETECTOR SELF-TESTS — pin the ported regex-normalization logic (layer
     classification, line normalization, trivial-line detection, cross-file
     duplicate detection). Always green: they prove the detector is healthy.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan the explicit
     ``ATDD_SCAN_ROOTS`` (with ``ATDD_SCAN_EXCLUDES``) and write the RAW
     structured violations to ``ATDD_VIOLATIONS_REPORT`` for ``run.py``.

This rule's disposition is ``strict``, but the detector still emits RAW only —
the verdict is the DOWNSTREAM CONSUMER's (PROVIDER-CONTRACT-v1.1 §1).

No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import duplication_typescript as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_layer_classification() -> None:
    assert detector.determine_layer_from_path(Path("web/src/domain/x.ts")) == "domain"
    assert detector.determine_layer_from_path(Path("web/src/hooks/x.ts")) == "application"
    assert detector.determine_layer_from_path(Path("web/src/components/x.tsx")) == "presentation"
    assert detector.determine_layer_from_path(Path("web/src/clients/x.ts")) == "integration"
    assert detector.determine_layer_from_path(Path("web/src/util/x.ts")) == "unknown"


def test_normalization_collapses_names_and_literals() -> None:
    a = detector._normalize_line('const userName = "alice";')
    b = detector._normalize_line('const orderId = "bob";')
    assert a == b  # identifiers -> ID, strings -> "S"


def test_trivial_lines_detected() -> None:
    assert detector._is_trivial_line("}") is True
    assert detector._is_trivial_line("") is True
    assert detector._is_trivial_line('const ID = 0;') is False


def test_excluded_files() -> None:
    assert detector.is_excluded(Path("a/x.test.ts")) is True
    assert detector.is_excluded(Path("a/x.spec.tsx")) is True
    assert detector.is_excluded(Path("a/x.d.ts")) is True
    assert detector.is_excluded(Path("a/index.ts")) is True
    assert detector.is_excluded(Path("a/widget.tsx")) is False


def test_real_shared_block_is_flagged() -> None:
    """Genuine duplicated block (>=7 normalized lines) across same-layer files."""
    a = _HERE / "fixtures" / "dirty" / "alpha" / "domain" / "alpha.ts"
    b = _HERE / "fixtures" / "dirty" / "beta" / "domain" / "beta.ts"
    v = detector.find_intra_layer_duplicates_ts({"domain": [a, b]}, 7)
    assert v, "copy-pasted same-layer block must be flagged"


def test_scan_emits_dup_rule_with_source_line() -> None:
    v = detector.scan_roots([_HERE / "fixtures" / "dirty"])
    assert v, "dirty fixture must yield at least one duplication violation"
    for item in v:
        assert item["rule_id"] == detector.RULE_DUP_TS
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
