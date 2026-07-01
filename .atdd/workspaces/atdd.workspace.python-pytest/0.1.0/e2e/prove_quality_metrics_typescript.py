"""End-to-end proof (Wave 2): the python-pytest provider discovers + runs the
MULTI-RULE TypeScript quality-metrics validator (coder.refactor.quality-mi-typescript
+ quality-comments-typescript), emits RAW structured multi-rule violations, and a
SEPARATE consumer-side disposition stand-in — applied AFTER the run — produces the
correct pass/fail.

Drives the REAL provider adapter (../adapter/discover.py + run.py) — no stubs —
and the REAL consumer stand-in (_consumer_disposition.py). Only the RAW violation
list crosses between them.

Both rule_ids are `strict` and PURE-REGEX (no radon — the TS MI is approximated):
  clean -> provider RAW = []                  -> disposition PASS
  dirty -> provider RAW = 2 over 2 rule_ids   -> disposition FAIL (2 unsuppressed)
          * mi-typescript: a dense, high-complexity .ts module scores MI < 20
          * comments-typescript: a .tsx module under the 10% comment ratio

Run:
    python3 official/atdd.workspace.python-pytest/e2e/prove_quality_metrics_typescript.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_WS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_WS / "adapter"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import discover as discover_mod  # noqa: E402
import run as run_mod  # noqa: E402
import _consumer_disposition as consumer  # noqa: E402

IMPLS_ROOT = _WS / "implementations"
IMPL_DIR = IMPLS_ROOT / "quality_metrics_typescript_detector"
EXPECTED_ID = "coder.refactor.quality-mi-typescript"

DISPOSITIONS = {
    "coder.refactor.quality-mi-typescript": "strict",
    "coder.refactor.quality-comments-typescript": "strict",
}
EXPECTED_RULES = set(DISPOSITIONS)


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

    _section("1. discover_implementations(implementations/)  [provider contract 1.1.0]")
    print(f"  provider CONTRACT_VERSION = {discover_mod.CONTRACT_VERSION}")
    found = discover_mod.discover_implementations(IMPLS_ROOT)
    if EXPECTED_ID in [i.implementation_id for i in found]:
        print(f"  PASS: discovered {EXPECTED_ID!r}")
    else:
        print(f"  FAIL: {EXPECTED_ID!r} not discovered")
        ok = False

    _section("2. fixtures/clean  -> expect RAW=[] -> disposition PASS")
    clean = _run_fixture("clean")
    _print_raw(clean)
    v_clean = consumer.apply_disposition(clean.violations, DISPOSITIONS)
    if clean.structured and clean.violations == [] and v_clean.passed:
        print("  PASS: clean fixture -> no raw violations -> PASS")
    else:
        print("  FAIL: expected empty raw + PASS")
        ok = False

    _section("3. fixtures/dirty  -> expect RAW over 2 rule_ids -> disposition FAIL")
    dirty = _run_fixture("dirty")
    _print_raw(dirty)
    v_dirty = consumer.apply_disposition(dirty.violations, DISPOSITIONS)
    dirty_rule_ids = {v["rule_id"] for v in dirty.violations}
    if (
        dirty.structured
        and EXPECTED_RULES <= dirty_rule_ids
        and not v_dirty.passed
        and len(v_dirty.unsuppressed) == len(dirty.violations)
    ):
        print(f"  PASS: emitted both rule_ids {sorted(r.split('.')[-1] for r in dirty_rule_ids)}")
        print(f"        all {len(v_dirty.unsuppressed)} raw violations unsuppressed (strict) -> FAIL")
        print("        ^ low-MI .ts module + uncommented .tsx module")
    else:
        print(f"  FAIL: expected {sorted(EXPECTED_RULES)} subset of {sorted(dirty_rule_ids)} -> FAIL")
        ok = False

    _section("RESULT")
    print("  ALL PASS — multi-rule TypeScript quality metrics proven end-to-end"
          if ok else "  FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
