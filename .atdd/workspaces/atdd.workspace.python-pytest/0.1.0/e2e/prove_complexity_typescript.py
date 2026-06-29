"""End-to-end proof (Wave 2): the python-pytest provider discovers + runs the
MULTI-RULE TypeScript complexity validator (coder.refactor.complexity-cyclomatic-
typescript + -nesting-typescript + -length-typescript — THREE strict rule_ids from
one run, detected by a regex/no-TS-runtime PYTHON detector), emits RAW structured
multi-rule violations, and a SEPARATE consumer-side disposition stand-in — applied
AFTER the run — produces the correct pass/fail.

Drives the REAL provider adapter (../adapter/discover.py + run.py) — no stubs —
and the REAL consumer stand-in (_consumer_disposition.py). Only the RAW violation
list crosses between them.

All three rule_ids are `strict`:
  clean -> provider RAW = []                  -> disposition PASS
  dirty -> provider RAW = 3 over 3 rule_ids   -> disposition FAIL (3 unsuppressed)
          * cyclomatic-typescript: classify (complexity > 10)
          * nesting-typescript:    deepNest (depth > 4)
          * length-typescript:     longFn   (LOC > 50)

NOTE: the core TS extractor has an off-by-one in `_find_opening_brace` that
truncates every function body to its signature line, making the core validator
inert. This detector applies a single documented off-by-one repair (see
implementations/complexity_typescript_detector/complexity_typescript.py) so the
metric functions the core author wrote actually run. See the migration report.

Run:
    python3 official/atdd.workspace.python-pytest/e2e/prove_complexity_typescript.py
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
IMPL_DIR = IMPLS_ROOT / "complexity_typescript_detector"
EXPECTED_ID = "coder.refactor.complexity-cyclomatic-typescript"

ALL_RULE_IDS = {
    "coder.refactor.complexity-cyclomatic-typescript",
    "coder.refactor.complexity-nesting-typescript",
    "coder.refactor.complexity-length-typescript",
}
DISPOSITIONS = {rid: "strict" for rid in ALL_RULE_IDS}


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
    for impl in found:
        if impl.implementation_id == EXPECTED_ID:
            print(f"  found: {impl.implementation_id}  contract={impl.contract_version}")
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
        print("  PASS: clean module -> no raw violations -> PASS")
    else:
        print("  FAIL: expected empty raw + PASS")
        ok = False

    _section("3. fixtures/dirty  -> expect RAW=3 over 3 rule_ids -> disposition FAIL")
    dirty = _run_fixture("dirty")
    _print_raw(dirty)
    v_dirty = consumer.apply_disposition(dirty.violations, DISPOSITIONS)
    dirty_rule_ids = {v["rule_id"] for v in dirty.violations}
    if (
        dirty.structured
        and len(dirty.violations) == 3
        and dirty_rule_ids == ALL_RULE_IDS
        and not v_dirty.passed
        and len(v_dirty.unsuppressed) == 3
    ):
        print("  PASS: 3 raw over 3 rule_ids -> FAIL, 3 unsuppressed (all strict)")
    else:
        print("  FAIL: expected 3 raw over 3 rule_ids -> strict FAIL")
        ok = False

    _section("RESULT")
    print("  ALL PASS — multi-rule TypeScript complexity (3 rule_ids) proven end-to-end"
          if ok else "  FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
