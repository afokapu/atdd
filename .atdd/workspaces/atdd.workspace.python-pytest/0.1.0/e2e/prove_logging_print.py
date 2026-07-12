"""End-to-end proof: the python-pytest provider discovers + runs the
coder.logging.print detector implementation and maps its result to the
violation-output contract.

Drives the REAL provider adapter (../adapter/discover.py + run.py) — no stubs.

  1. discover_implementations(implementations/) finds the manifest.
  2. run_implementation(...) with the default env  -> GREEN, zero violations.
  3. run_implementation(...) with ATDD_SCAN_TARGET=fixtures/dirty
                                                   -> RED, one violation whose
     rule_id == coder.logging.print.

Exit 0 only if all three assertions hold. Run:
    python3 official/atdd.workspace.python-pytest/e2e/prove_logging_print.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_WS = Path(__file__).resolve().parent.parent  # atdd.workspace.python-pytest/
sys.path.insert(0, str(_WS / "adapter"))

import discover as discover_mod  # noqa: E402
import run as run_mod  # noqa: E402

IMPLS_ROOT = _WS / "implementations"
IMPL_DIR = IMPLS_ROOT / "logging_print_detector"
EXPECTED_ID = "coder.logging.print"


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    ok = True

    # 1. DISCOVER ──────────────────────────────────────────────────────────────
    _section("1. discover_implementations(implementations/)")
    found = discover_mod.discover_implementations(IMPLS_ROOT)
    for impl in found:
        print(f"  found: {impl.implementation_id}  contract={impl.contract_version}  "
              f"targets={impl.targets_workspace}")
    discovered_ids = [i.implementation_id for i in found]
    if EXPECTED_ID in discovered_ids:
        print(f"  PASS: discovered {EXPECTED_ID!r}")
    else:
        print(f"  FAIL: {EXPECTED_ID!r} not in {discovered_ids}")
        ok = False

    # 2. RUN — default env -> GREEN ────────────────────────────────────────────
    _section("2. run_implementation(default env)  -> expect GREEN, no violations")
    green = run_mod.run_implementation(EXPECTED_ID, IMPL_DIR)
    print(f"  ran={green.ran} passed={green.passed} exit={green.exit_code} "
          f"violations={green.violations}")
    print("  --- pytest summary ---")
    print("  " + (green.stdout.strip().splitlines()[-1] if green.stdout.strip() else "<none>"))
    if green.ran and green.passed and green.exit_code == 0 and green.violations == []:
        print("  PASS: clean target -> no violation")
    else:
        print("  FAIL: expected a clean GREEN run")
        ok = False

    # 3. RUN — dirty target -> RED with rule_id ────────────────────────────────
    _section("3. run_implementation(ATDD_SCAN_TARGET=fixtures/dirty)  -> expect RED + violation")
    dirty_env = {**os.environ, "ATDD_SCAN_TARGET": "fixtures/dirty"}
    red = run_mod.run_implementation(EXPECTED_ID, IMPL_DIR, env=dirty_env)
    print(f"  ran={red.ran} passed={red.passed} exit={red.exit_code}")
    print(f"  violations={red.violations}")
    print("  --- pytest summary ---")
    print("  " + (red.stdout.strip().splitlines()[-1] if red.stdout.strip() else "<none>"))
    if (
        red.ran
        and not red.passed
        and red.exit_code == 1
        and len(red.violations) == 1
        and red.violations[0]["rule_id"] == EXPECTED_ID
    ):
        print(f"  PASS: dirty target -> violation rule_id={red.violations[0]['rule_id']!r}")
    else:
        print("  FAIL: expected one RED violation keyed by the rule_id")
        ok = False

    _section("RESULT")
    print("  ALL PASS — end-to-end contract proven" if ok else "  FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
