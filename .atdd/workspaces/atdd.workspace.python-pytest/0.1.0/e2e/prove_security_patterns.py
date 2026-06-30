"""End-to-end proof (Wave 2): the python-pytest provider discovers + runs the
STRICT security-patterns validator (coder.security.sql-injection +
coder.security.missing-auth + coder.security.hardcoded-secret, python stack),
emits RAW structured multi-rule violations, and a SEPARATE consumer-side
disposition stand-in — applied AFTER the run — produces the correct pass/fail.

Drives the REAL provider adapter (../adapter/discover.py + run.py) — no stubs —
and the REAL consumer stand-in (_consumer_disposition.py). Only the RAW violation
list crosses between them.

All three rule_ids are `strict`:
  clean -> provider RAW = []                          -> disposition PASS
  dirty -> provider RAW = 4 over 3 rule_ids           -> disposition FAIL (4 unsuppressed)
          * sql-injection:   "SELECT ..." + name concatenation into .execute()
          * missing-auth:    @router.get route with no Depends(<auth_fn>)
          * hardcoded-secret: an AWS key literal + a password literal (2 sites)

Run:
    python3 official/atdd.workspace.python-pytest/e2e/prove_security_patterns.py
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
IMPL_DIR = IMPLS_ROOT / "security_patterns_detector"
EXPECTED_ID = "coder.security.sql-injection"

DISPOSITIONS = {
    "coder.security.sql-injection": "strict",
    "coder.security.missing-auth": "strict",
    "coder.security.hardcoded-secret": "strict",
}
EXPECTED_RULE_IDS = set(DISPOSITIONS)


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def _run_fixture(name: str) -> run_mod.RunResult:
    return run_mod.run_implementation(EXPECTED_ID, IMPL_DIR, scan_roots=[f"fixtures/{name}"])


def _print_raw(res: run_mod.RunResult) -> None:
    print(f"  structured={res.structured} ran={res.ran} passed={res.passed} "
          f"exit={res.exit_code}  RAW violations={len(res.violations)}")
    for v in res.violations:
        print(f"    - [{v['rule_id']}] {v['file']}:{v['line']}:{v['col']}")
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
        print("  PASS: clean -> no raw violations -> PASS")
    else:
        print("  FAIL: expected empty raw + PASS")
        ok = False

    _section("3. fixtures/dirty  -> expect RAW=4 over 3 rule_ids -> disposition FAIL")
    dirty = _run_fixture("dirty")
    _print_raw(dirty)
    v_dirty = consumer.apply_disposition(dirty.violations, DISPOSITIONS)
    dirty_rule_ids = {v["rule_id"] for v in dirty.violations}
    if (
        dirty.structured
        and len(dirty.violations) == 4
        and dirty_rule_ids == EXPECTED_RULE_IDS
        and not v_dirty.passed
        and len(v_dirty.unsuppressed) == 4
    ):
        print("  PASS: 4 raw over 3 strict rule_ids -> FAIL, 4 unsuppressed")
        print("        ^ dynamic SQL + unauthenticated route + 2 secret literals")
    else:
        print("  FAIL: expected 4 raw over 3 rule_ids -> strict FAIL")
        ok = False

    _section("RESULT")
    print("  ALL PASS — strict security-patterns (python) proven end-to-end"
          if ok else "  FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
