"""Runnable enforcement for coder.duplication.no-intra-layer-code-python.

What the provider's ``pytest`` command collects. Two layers:

  1. DETECTOR SELF-TESTS — pin the ported AST logic (layer classification,
     fragment hashing, header stripping, cross-file duplicate detection).
     Always green: they prove the detector itself is healthy.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan the explicit
     ``ATDD_SCAN_ROOTS`` (with ``ATDD_SCAN_EXCLUDES``) and write the RAW
     structured violations to ``ATDD_VIOLATIONS_REPORT`` for ``run.py``.

This rule's disposition is ``strict``, but the detector still emits RAW only —
the strict pass/fail verdict is the DOWNSTREAM CONSUMER's (PROVIDER-CONTRACT-v1.1
§1). The test passes once it has emitted; the pytest exit code is run-health.

No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import duplication as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_layer_classification() -> None:
    assert detector.determine_layer_from_path(Path("a/domain/x.py")) == "domain"
    assert detector.determine_layer_from_path(Path("a/use_cases/x.py")) == "application"
    assert detector.determine_layer_from_path(Path("a/controllers/x.py")) == "presentation"
    assert detector.determine_layer_from_path(Path("a/adapters/x.py")) == "integration"
    assert detector.determine_layer_from_path(Path("a/util/x.py")) == "unknown"


def test_header_boilerplate_only_overlap_is_not_flagged() -> None:
    """Two same-layer files sharing only standard header boilerplate aren't flagged."""
    shared_header = (
        '"""{title} value object."""\n'
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        "from typing import Optional\n"
        "_RULE = 1\n"
    )
    a = _HERE / "fixtures" / "clean" / "record" / "domain" / "record.py"
    b = _HERE / "fixtures" / "clean" / "verdict" / "domain" / "verdict.py"
    v = detector.find_intra_layer_duplicates({"domain": [a, b]}, 5)
    assert v == []  # the clean fixtures share only headers + distinct bodies


def test_real_shared_body_is_flagged() -> None:
    """Genuine duplicated body logic across same-layer files IS flagged."""
    a = _HERE / "fixtures" / "dirty" / "alpha" / "domain" / "alpha.py"
    b = _HERE / "fixtures" / "dirty" / "beta" / "domain" / "beta.py"
    v = detector.find_intra_layer_duplicates({"domain": [a, b]}, 5)
    assert v, "copy-pasted same-layer body logic must be flagged"


def test_test_and_init_files_are_excluded() -> None:
    assert detector.is_excluded(Path("pkg/test_x.py")) is True
    assert detector.is_excluded(Path("pkg/tests/h.py")) is True
    assert detector.is_excluded(Path("pkg/conftest.py")) is True
    assert detector.is_excluded(Path("pkg/__init__.py")) is True
    assert detector.is_excluded(Path("pkg/service.py")) is False


def test_scan_emits_dup_rule_with_source_line() -> None:
    """Scanning the dirty fixture emits the python dup rule_id with source_line."""
    v = detector.scan_roots([_HERE / "fixtures" / "dirty"])
    assert v, "dirty fixture must yield at least one duplication violation"
    for item in v:
        assert item["rule_id"] == detector.RULE_DUP_PY
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
    """Scan the supplied roots and emit the RAW violation report (no verdict)."""
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
