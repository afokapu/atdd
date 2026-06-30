"""Runnable enforcement for coder.logging.print under the python-pytest provider.

This file is what the provider's ``pytest`` command collects. Two layers:

  1. DETECTOR SELF-TESTS — pin the ported AST logic's behavior (clean -> none,
     print -> found, method-print -> ignored, syntax error -> none, exclusions).
     These are always green; they prove the detector itself is healthy.

  2. ENFORCEMENT — scan a target tree and assert it is print-free. The target is
     ``$ATDD_SCAN_TARGET`` (resolved relative to this file), defaulting to
     ``fixtures/clean``. Default run -> GREEN (exit 0 -> provider: no violation).
     Run with ATDD_SCAN_TARGET=fixtures/dirty -> RED (exit 1 -> provider emits a
     violation keyed by the implementation_id == coder.logging.print).

No core (``atdd.coach.*``) imports; the detector is imported by path like the
github-extension implementations do.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import logging_print as detector  # noqa: E402

_HERE = Path(__file__).resolve().parent


# ── 1. detector self-tests ────────────────────────────────────────────────────


def test_clean_source_has_no_violations() -> None:
    assert detector.detect_print_calls("logger.info('hi', extra={})\n") == []


def test_bare_print_is_detected() -> None:
    hits = detector.detect_print_calls("print('x')\n")
    assert len(hits) == 1
    assert hits[0][0] == 1  # lineno


def test_method_named_print_is_not_flagged() -> None:
    # obj.print(...) is an attribute call, not the builtin — must be ignored.
    assert detector.detect_print_calls("writer.print('x')\n") == []


def test_unparseable_source_yields_no_violations() -> None:
    assert detector.detect_print_calls("def (:\n") == []


def test_test_and_init_files_are_excluded() -> None:
    assert detector.is_excluded(Path("pkg/test_thing.py")) is True
    assert detector.is_excluded(Path("pkg/tests/helper.py")) is True
    assert detector.is_excluded(Path("pkg/__init__.py")) is True
    assert detector.is_excluded(Path("pkg/service.py")) is False


def test_scan_path_reports_rule_id_and_location() -> None:
    v = detector.scan_path(_HERE / "fixtures" / "dirty")
    assert v, "dirty fixture must produce violations"
    assert all(item["rule_id"] == "coder.logging.print" for item in v)
    assert any("service.py:" in item["location"] for item in v)


def test_scan_path_honors_exclude_globs() -> None:
    """ATDD_SCAN_EXCLUDES drops matching paths (the bug fix, PHASE0-PROOF G2).

    Before the fix this detector SILENTLY IGNORED excludes — only the
    structured_logging detector honored them. With no excludes the excludable
    tree flags BOTH print sites; excluding ``generated/*`` (a root-relative glob,
    matched the same way structured_logging matches its excludes) must drop the
    generated one and keep the top-level one.
    """
    tree = _HERE / "fixtures" / "excludable"

    no_excludes = detector.scan_path(tree)
    locations = {v["location"] for v in no_excludes}
    assert any(loc.startswith("app.py:") for loc in locations)
    assert any(loc.startswith("generated/legacy.py:") for loc in locations)

    excluded = detector.scan_path(tree, ["generated/*"])
    excl_locations = {v["location"] for v in excluded}
    # the generated/ print is gone …
    assert not any(loc.startswith("generated/legacy.py:") for loc in excl_locations), (
        f"excluded path was still flagged: {excl_locations}"
    )
    # … and the non-excluded print is still caught (excludes are precise).
    assert any(loc.startswith("app.py:") for loc in excl_locations)


# ── 2. enforcement (the assertion the provider's exit code reflects) ──────────


def _scan_target() -> Path:
    raw = os.environ.get("ATDD_SCAN_TARGET", "fixtures/clean")
    target = Path(raw)
    return target if target.is_absolute() else (_HERE / target)


def _exclude_globs() -> list[str]:
    """Parse ATDD_SCAN_EXCLUDES (JSON list) — the §2 exclusion-glob channel.

    Mirrors structured_logging's reader so this detector obeys the same
    scan-mount inputs the provider injects. Absent/malformed -> no excludes.
    """
    raw = os.environ.get("ATDD_SCAN_EXCLUDES")
    if not raw:
        return []
    try:
        globs = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(g) for g in globs] if isinstance(globs, list) else []


def test_scan_target_is_print_free() -> None:
    """Production code under the scan target must not use builtin print().

    Disposition for coder.logging.print is `strict` (per the convention node):
    any violation fails. Green by default (fixtures/clean); RED when pointed at
    a tree that contains print(). Honors ATDD_SCAN_EXCLUDES so an excluded path
    is not falsely flagged."""
    target = _scan_target()
    violations = detector.scan_path(target, _exclude_globs())
    assert violations == [], (
        f"{len(violations)} coder.logging.print violation(s) under {target}:\n"
        + "\n".join(f"  - {v['location']}: {v['evidence']}" for v in violations)
    )
