"""End-to-end proof: the python-pytest provider discovers + runs the NON-STRICT
validator coder.logging.coach-silent-swallow (disposition suppress-and-clean,
severity 4), emits RAW structured violations, and a SEPARATE consumer-side
disposition stand-in — applied AFTER the run — produces the correct pass/fail.

Drives the REAL provider adapter (../adapter/discover.py + run.py) — no stubs —
and the REAL consumer stand-in (_consumer_disposition.py). The adapter and the
stand-in never import each other; only the RAW violation list crosses between.

Proves, per fixture:
  clean          -> provider RAW = []           -> disposition PASS
  dirty          -> provider RAW = 3            -> disposition FAIL (2 unsuppressed)
  all_suppressed -> provider RAW = 2 (NON-EMPTY)-> disposition PASS (all absorbed)  <-- crux

Exit 0 only if every assertion holds. Run:
    python3 official/atdd.workspace.python-pytest/e2e/prove_silent_swallow.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_WS = Path(__file__).resolve().parent.parent  # atdd.workspace.python-pytest/
sys.path.insert(0, str(_WS / "adapter"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _consumer_disposition

import discover as discover_mod  # noqa: E402
import run as run_mod  # noqa: E402
import _consumer_disposition as consumer  # noqa: E402

IMPLS_ROOT = _WS / "implementations"
IMPL_DIR = IMPLS_ROOT / "silent_swallow_detector"
EXPECTED_ID = "coder.logging.coach-silent-swallow"

# The disposition registry a real consumer would build from the convention node.
DISPOSITIONS = {EXPECTED_ID: "suppress-and-clean"}


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def _run_fixture(name: str) -> run_mod.RunResult:
    return run_mod.run_implementation(EXPECTED_ID, IMPL_DIR, scan_roots=[f"fixtures/{name}"])


def _print_raw(res: run_mod.RunResult) -> None:
    print(f"  structured={res.structured} ran={res.ran} passed={res.passed} "
          f"exit={res.exit_code}  RAW violations={len(res.violations)}")
    for v in res.violations:
        print(f"    - [{v['rule_id']}] {v['file']}:{v['line']}:{v['col']}  "
              f"src={v['source_line'].strip()!r}")


def _print_verdict(verdict: consumer.Verdict) -> None:
    print(f"  consumer disposition verdict: {'PASS' if verdict.passed else 'FAIL'}  "
          f"(unsuppressed={len(verdict.unsuppressed)}, suppressed={len(verdict.suppressed)})")
    for rid, b in sorted(verdict.by_rule.items()):
        print(f"      {rid} [{b['disposition']}]: "
              f"{b['unsuppressed']} unsuppressed, {b['suppressed']} suppressed")


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
    _print_verdict(v_clean)
    if clean.structured and clean.violations == [] and v_clean.passed:
        print("  PASS: clean -> no raw violations -> PASS")
    else:
        print("  FAIL: expected empty raw + PASS")
        ok = False

    _section("3. fixtures/dirty  -> expect RAW=3 -> disposition FAIL (2 unsuppressed)")
    dirty = _run_fixture("dirty")
    _print_raw(dirty)
    v_dirty = consumer.apply_disposition(dirty.violations, DISPOSITIONS)
    _print_verdict(v_dirty)
    if (
        dirty.structured
        and len(dirty.violations) == 3
        and {v["rule_id"] for v in dirty.violations} == {EXPECTED_ID}
        and not v_dirty.passed
        and len(v_dirty.unsuppressed) == 2
        and len(v_dirty.suppressed) == 1
    ):
        print("  PASS: 3 raw -> FAIL, 2 unsuppressed / 1 suppressed")
    else:
        print("  FAIL: expected 3 raw -> FAIL with 2 unsuppressed / 1 suppressed")
        ok = False

    _section("4. fixtures/all_suppressed  -> expect RAW NON-EMPTY -> disposition PASS")
    allsup = _run_fixture("all_suppressed")
    _print_raw(allsup)
    v_allsup = consumer.apply_disposition(allsup.violations, DISPOSITIONS)
    _print_verdict(v_allsup)
    if (
        allsup.structured
        and len(allsup.violations) == 2
        and {v["rule_id"] for v in allsup.violations} == {EXPECTED_ID}
        and v_allsup.passed
        and len(v_allsup.suppressed) == 2
        and len(v_allsup.unsuppressed) == 0
    ):
        print("  PASS: provider emits 2 RAW, consumer absorbs both -> PASS")
        print("        ^ disposition decided ENTIRELY downstream — separability proven")
    else:
        print("  FAIL: expected RAW non-empty + verdict PASS via suppression")
        ok = False

    _section("RESULT")
    print("  ALL PASS — suppress-and-clean swallow proof green; disposition cleanly separable"
          if ok else "  FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
