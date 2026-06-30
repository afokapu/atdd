"""End-to-end proof (Wave 2): the python-pytest provider discovers + runs the
multi-rule design-system-compliance validator (SEVEN strict coder.design.* rule
ids, web stack), emits RAW structured multi-rule violations, and a SEPARATE
consumer-side disposition stand-in — applied AFTER the run — produces the correct
pass/fail.

Drives the REAL provider adapter (../adapter/discover.py + run.py) — no stubs —
and the REAL consumer stand-in (_consumer_disposition.py). Only the RAW violation
list crosses between them.

All seven rule_ids are `strict`:
  clean -> provider RAW = []                  -> disposition PASS
  dirty -> provider RAW = 7 over 7 rule_ids   -> disposition FAIL (7 unsuppressed)
          one violation per rule:
            primitives        presentation .tsx renders JSX, no DS import
            token-color       UI file embeds a raw hex literal
            orphan-export     a DS export no consumer imports
            foundations       a DS primitive embeds a raw pixel literal
            hierarchy-import  a primitive imports up into components
            token-hardcoded   a UI file hardcodes a pixel spacing value
            orphan-ui         a rendering .tsx imports nothing from the DS

Run:
    python3 official/atdd.workspace.python-pytest/e2e/prove_design_system_compliance.py
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
IMPL_DIR = IMPLS_ROOT / "design_system_compliance_detector"
EXPECTED_ID = "coder.design.primitives"

EXPECTED_RULE_IDS = {
    "coder.design.primitives",
    "coder.design.token-color",
    "coder.design.orphan-export",
    "coder.design.foundations",
    "coder.design.hierarchy-import",
    "coder.design.token-hardcoded",
    "coder.design.orphan-ui",
}

# All seven coder.design.* rules are strict (per the migrated convention nodes).
DISPOSITIONS = {rid: "strict" for rid in EXPECTED_RULE_IDS}


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
        print("  PASS: clean design system -> no raw violations -> PASS")
    else:
        print("  FAIL: expected empty raw + PASS")
        ok = False

    _section("3. fixtures/dirty  -> expect RAW=7 over 7 rule_ids -> disposition FAIL")
    dirty = _run_fixture("dirty")
    _print_raw(dirty)
    v_dirty = consumer.apply_disposition(dirty.violations, DISPOSITIONS)
    dirty_rule_ids = {v["rule_id"] for v in dirty.violations}
    if (
        dirty.structured
        and len(dirty.violations) == 7
        and dirty_rule_ids == EXPECTED_RULE_IDS
        and not v_dirty.passed
        and len(v_dirty.unsuppressed) == 7
    ):
        print("  PASS: 7 raw over 7 rule_ids -> FAIL, 7 unsuppressed (all strict)")
    else:
        print("  FAIL: expected 7 raw over 7 rule_ids -> strict FAIL")
        ok = False

    _section("RESULT")
    print("  ALL PASS — strict design-system compliance (web) proven end-to-end"
          if ok else "  FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
