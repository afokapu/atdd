"""End-to-end proof (Wave 2): the python-pytest provider discovers + runs the
MULTI-RULE quality-metrics validator (python stack — coder.refactor.quality-mi +
quality-comments + quality-duplication + quality-naming + quality-file-length),
emits RAW structured multi-rule violations, and a SEPARATE consumer-side
disposition stand-in — applied AFTER the run — produces the correct pass/fail.

Drives the REAL provider adapter (../adapter/discover.py + run.py) — no stubs —
and the REAL consumer stand-in (_consumer_disposition.py). Only the RAW violation
list crosses between them.

All five rule_ids are `strict`:
  clean -> provider RAW = []                  -> disposition PASS
  dirty -> provider RAW >= 4 over >= 4 rules  -> disposition FAIL (all unsuppressed)

SUBSTRATE NOTE (honest): coder.refactor.quality-mi is radon-coupled. radon is not
installed in this worktree, so the MI leg emits nothing here (the faithful 100.0
fallback) and the proof asserts the four PURE-STDLIB rule_ids
(comments / duplication / naming / file-length). When radon IS present the MI rule
fires too (proven by the detector self-test test_mi_leg_matches_radon_availability).

Run:
    python3 official/atdd.workspace.python-pytest/e2e/prove_quality_metrics.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_WS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_WS / "adapter"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(_WS / "implementations" / "quality_metrics_detector"))

import discover as discover_mod  # noqa: E402
import run as run_mod  # noqa: E402
import _consumer_disposition as consumer  # noqa: E402
import quality_metrics as detector  # noqa: E402

IMPLS_ROOT = _WS / "implementations"
IMPL_DIR = IMPLS_ROOT / "quality_metrics_detector"
EXPECTED_ID = "coder.refactor.quality-mi"

# All five python quality rule_ids are strict (refactor.convention.yaml rules[]).
DISPOSITIONS = {
    "coder.refactor.quality-mi": "strict",
    "coder.refactor.quality-comments": "strict",
    "coder.refactor.quality-duplication": "strict",
    "coder.refactor.quality-naming": "strict",
    "coder.refactor.quality-file-length": "strict",
}

# The rule_ids that fire deterministically regardless of radon availability.
STDLIB_RULES = {
    "coder.refactor.quality-comments",
    "coder.refactor.quality-duplication",
    "coder.refactor.quality-naming",
    "coder.refactor.quality-file-length",
}


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def _run_fixture(name: str) -> run_mod.RunResult:
    return run_mod.run_implementation(EXPECTED_ID, IMPL_DIR, scan_roots=[f"fixtures/{name}"])


def _print_raw(res: run_mod.RunResult) -> None:
    print(f"  structured={res.structured} ran={res.ran} passed={res.passed} "
          f"exit={res.exit_code}  RAW violations={len(res.violations)}")
    for v in res.violations:
        print(f"    - [{v['rule_id']}] {v['file']}:{v['line']}")
        print(f"        {v['evidence']}")


def main() -> int:
    ok = True
    radon = detector.radon_available()

    _section("1. discover_implementations(implementations/)  [provider contract 1.1.0]")
    print(f"  provider CONTRACT_VERSION = {discover_mod.CONTRACT_VERSION}")
    found = discover_mod.discover_implementations(IMPLS_ROOT)
    if EXPECTED_ID in [i.implementation_id for i in found]:
        print(f"  PASS: discovered {EXPECTED_ID!r}")
    else:
        print(f"  FAIL: {EXPECTED_ID!r} not discovered")
        ok = False

    print(f"  radon available in this env: {radon}  "
          f"({'MI leg exercised' if radon else 'MI leg SKIPPED — substrate-coupled, documented'})")

    _section("2. fixtures/clean  -> expect RAW=[] -> disposition PASS")
    clean = _run_fixture("clean")
    _print_raw(clean)
    v_clean = consumer.apply_disposition(clean.violations, DISPOSITIONS)
    if clean.structured and clean.violations == [] and v_clean.passed:
        print("  PASS: clean fixture -> no raw violations -> PASS")
    else:
        print("  FAIL: expected empty raw + PASS")
        ok = False

    _section("3. fixtures/dirty  -> expect RAW over multiple rule_ids -> disposition FAIL")
    dirty = _run_fixture("dirty")
    _print_raw(dirty)
    v_dirty = consumer.apply_disposition(dirty.violations, DISPOSITIONS)
    dirty_rule_ids = {v["rule_id"] for v in dirty.violations}

    expected = set(STDLIB_RULES)
    if radon:
        expected = expected | {"coder.refactor.quality-mi"}

    checks = (
        dirty.structured
        and expected <= dirty_rule_ids
        and not v_dirty.passed
        and len(v_dirty.unsuppressed) == len(dirty.violations)
        and len(dirty.violations) >= 4
    )
    if checks:
        print(f"  PASS: emitted rule_ids {sorted(r.split('.')[-1] for r in dirty_rule_ids)}")
        print(f"        all {len(v_dirty.unsuppressed)} raw violations unsuppressed (strict) -> FAIL")
        if not radon:
            print("        NOTE: quality-mi correctly ABSENT (radon unavailable — faithful 100.0 fallback)")
    else:
        print(f"  FAIL: expected {sorted(expected)} subset of {sorted(dirty_rule_ids)} -> strict FAIL")
        ok = False

    _section("RESULT")
    print("  ALL PASS — multi-rule python quality metrics proven end-to-end"
          if ok else "  FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
