"""Runnable enforcement for coder.error-response.bare-string + .code-format.

What the provider's ``pytest`` command collects. Two layers:

  1. DETECTOR SELF-TESTS — pin the ported regexes (bare-string detection,
     UPPER_SNAKE_CASE error-code detection, dict-detail is clean). Always green.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan the explicit
     ``ATDD_SCAN_ROOTS`` (with ``ATDD_SCAN_EXCLUDES``) and write the RAW
     structured violations (BOTH rule_ids) to ``ATDD_VIOLATIONS_REPORT``.

Both rules are ``strict``, but the detector still emits RAW only — the verdict is
the DOWNSTREAM CONSUMER's (PROVIDER-CONTRACT-v1.1 §1). One run carries BOTH
rule_ids (multi-rule, gap 3).

No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import error_response as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_bare_string_detail_is_detected() -> None:
    src = 'raise HTTPException(status_code=400, detail="bad request")\n'
    hits = detector.detect_bare_string_details(src)
    assert len(hits) == 1


def test_fstring_detail_is_detected() -> None:
    src = 'raise HTTPException(status_code=404, detail=f"User {uid} not found")\n'
    assert len(detector.detect_bare_string_details(src)) == 1


def test_dict_detail_is_clean() -> None:
    src = (
        'raise HTTPException(status_code=400, detail={\n'
        '    "status_code": 400, "error_code": "INVALID_INPUT", "message": "x"})\n'
    )
    assert detector.detect_bare_string_details(src) == []


def test_lowercase_error_code_is_detected() -> None:
    src = '{"error_code": "bad_input", "message": "x"}\n'
    hits = detector.detect_bad_error_codes(src)
    assert len(hits) == 1
    assert hits[0][1] == "bad_input"


def test_upper_snake_error_code_is_clean() -> None:
    src = '{"error_code": "INVALID_INPUT"}\n'
    assert detector.detect_bad_error_codes(src) == []


def test_scan_emits_both_rule_ids_with_source_line() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    rule_ids = {item["rule_id"] for item in v}
    assert detector.RULE_BARE_STRING in rule_ids
    assert detector.RULE_CODE_FORMAT in rule_ids
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
