"""Runnable enforcement for coder.boundaries.http-client.

What the provider's ``pytest`` command collects. Two layers:

  1. DETECTOR SELF-TESTS — pin the ported regex (raw fetch() found; obj.fetch /
     prefetch ignored; comment lines skipped; test files excluded; whitelist as
     scan-exclude honored). Always green.

  2. EMISSION (the v1.1 contract job, NOT a verdict) — scan the explicit
     ``ATDD_SCAN_ROOTS`` (with ``ATDD_SCAN_EXCLUDES`` carrying the consumer's
     whitelist) and write the RAW structured violations to
     ``ATDD_VIOLATIONS_REPORT``.

This rule is ``strict``, but the detector still emits RAW only — the verdict is
the DOWNSTREAM CONSUMER's (PROVIDER-CONTRACT-v1.1 §1).

No core (``atdd.coach.*``) imports; the detector is imported by path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract_driven_http as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent

CONTRACT_VERSION = "1.1.0"
ENV_SCAN_ROOTS = "ATDD_SCAN_ROOTS"
ENV_SCAN_EXCLUDES = "ATDD_SCAN_EXCLUDES"
ENV_REPORT = "ATDD_VIOLATIONS_REPORT"


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_raw_fetch_is_detected() -> None:
    assert len(detector.detect_raw_fetch("const r = await fetch(url);\n")) == 1


def test_property_and_prefetch_are_ignored() -> None:
    assert detector.detect_raw_fetch("this.fetch(url);\n") == []
    assert detector.detect_raw_fetch("prefetch(url);\n") == []


def test_comment_lines_are_skipped() -> None:
    assert detector.detect_raw_fetch("// const r = fetch(url);\n") == []
    assert detector.detect_raw_fetch("/* fetch(url) */\n") == []


def test_test_files_excluded() -> None:
    assert detector.is_test_file(Path("a/x.test.ts")) is True
    assert detector.is_test_file(Path("a/x.spec.tsx")) is True
    assert detector.is_test_file(Path("a/__tests__/x.ts")) is True
    assert detector.is_test_file(Path("a/client.ts")) is False


def test_whitelist_as_exclude_is_honored() -> None:
    """A whitelisted (excluded) file yields no violation."""
    root = _HERE / "fixtures" / "dirty"
    assert detector.scan_root(root) != []                    # offender present
    assert detector.scan_root(root, ["api/client.ts"]) == []  # whitelisted away


def test_scan_emits_http_rule_with_source_line() -> None:
    v = detector.scan_root(_HERE / "fixtures" / "dirty")
    assert v
    for item in v:
        assert item["rule_id"] == detector.RULE_HTTP_CLIENT
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
