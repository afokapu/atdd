"""End-to-end RE-PROOF (Phase 0.5): the python-pytest provider discovers + runs a
NON-STRICT validator (coder.logging.structured, disposition suppress-and-clean),
emits RAW structured multi-rule violations, and a SEPARATE consumer-side
disposition stand-in — applied AFTER the run — produces the correct pass/fail.

Drives the REAL provider adapter (../adapter/discover.py + run.py) — no stubs —
and the REAL consumer stand-in (_consumer_disposition.py). The adapter and the
stand-in never import each other; only the RAW violation list crosses between.

Proves, per fixture:
  clean          -> provider RAW = []            -> disposition PASS
  dirty          -> provider RAW = 3 (2 rule_ids) -> disposition FAIL (2 unsuppressed)
  all_suppressed -> provider RAW = 2 (NON-EMPTY)  -> disposition PASS (all absorbed)  <-- crux

Exit 0 only if every assertion holds. Run:
    python3 official/atdd.workspace.python-pytest/e2e/prove_structured_logging.py
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
IMPL_DIR = IMPLS_ROOT / "structured_logging_detector"
EXPECTED_ID = "coder.logging.structured"


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def _run_fixture(name: str) -> run_mod.RunResult:
    """Run the provider over one fixture as its explicit single scan root."""
    return run_mod.run_implementation(
        EXPECTED_ID, IMPL_DIR, scan_roots=[f"fixtures/{name}"]
    )


def _print_raw(res: run_mod.RunResult) -> None:
    print(f"  structured={res.structured} ran={res.ran} passed={res.passed} "
          f"exit={res.exit_code}  RAW violations={len(res.violations)}")
    for v in res.violations:
        print(f"    - [{v['rule_id']}] {v['file']}:{v['line']}:{v['col']}  "
              f"src={v['source_line'].strip()!r}")


def _print_verdict(label: str, verdict: consumer.Verdict) -> None:
    print(f"  consumer disposition verdict: "
          f"{'PASS' if verdict.passed else 'FAIL'}  "
          f"(unsuppressed={len(verdict.unsuppressed)}, "
          f"suppressed={len(verdict.suppressed)})")
    for rid, b in sorted(verdict.by_rule.items()):
        print(f"      {rid} [{b['disposition']}]: "
              f"{b['unsuppressed']} unsuppressed, {b['suppressed']} suppressed")


def main() -> int:
    ok = True

    # 1. DISCOVER ──────────────────────────────────────────────────────────────
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

    # 2. clean -> RAW empty -> PASS ─────────────────────────────────────────────
    _section("2. fixtures/clean  -> expect RAW=[] -> disposition PASS")
    clean = _run_fixture("clean")
    _print_raw(clean)
    v_clean = consumer.apply_disposition(clean.violations)
    _print_verdict("clean", v_clean)
    if clean.structured and clean.violations == [] and v_clean.passed:
        print("  PASS: clean -> no raw violations -> PASS")
    else:
        print("  FAIL: expected empty raw + PASS")
        ok = False

    # 3. dirty -> RAW 3 (2 rule_ids) -> FAIL (2 unsuppressed) ───────────────────
    _section("3. fixtures/dirty  -> expect RAW=3 over 2 rule_ids -> disposition FAIL")
    dirty = _run_fixture("dirty")
    _print_raw(dirty)
    v_dirty = consumer.apply_disposition(dirty.violations)
    _print_verdict("dirty", v_dirty)
    dirty_rule_ids = {v["rule_id"] for v in dirty.violations}
    if (
        dirty.structured
        and len(dirty.violations) == 3
        and dirty_rule_ids == {"coder.logging.print", "coder.logging.structured"}
        and not v_dirty.passed
        and len(v_dirty.unsuppressed) == 2
        and len(v_dirty.suppressed) == 1
    ):
        print("  PASS: 3 raw (print+structured) -> FAIL, 2 unsuppressed / 1 suppressed")
    else:
        print("  FAIL: expected 3 raw over 2 rule_ids -> FAIL with 2 unsuppressed")
        ok = False

    # 4. all_suppressed -> RAW NON-EMPTY -> PASS  (the crux) ────────────────────
    _section("4. fixtures/all_suppressed  -> expect RAW NON-EMPTY -> disposition PASS")
    allsup = _run_fixture("all_suppressed")
    _print_raw(allsup)
    v_allsup = consumer.apply_disposition(allsup.violations)
    _print_verdict("all_suppressed", v_allsup)
    if (
        allsup.structured
        and len(allsup.violations) == 2          # provider emits RAW non-empty
        and {v["rule_id"] for v in allsup.violations} == {"coder.logging.structured"}
        and v_allsup.passed                       # ...yet the verdict is PASS
        and len(v_allsup.suppressed) == 2
        and len(v_allsup.unsuppressed) == 0
    ):
        print("  PASS: provider emits 2 RAW, consumer absorbs both -> PASS")
        print("        ^ disposition decided ENTIRELY downstream — separability proven")
    else:
        print("  FAIL: expected RAW non-empty + verdict PASS via suppression")
        ok = False

    _section("RESULT")
    print("  ALL PASS — non-strict re-proof green; disposition cleanly separable"
          if ok else "  FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
