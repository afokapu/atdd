"""End-to-end proof (Wave 2): the python-pytest provider discovers + runs the
MIXED-DISPOSITION cross-language-consistency validator (coder.boundaries.xlang-
entity + -enum + -naming + -contract), emits RAW structured multi-rule
violations, and a SEPARATE consumer-side disposition stand-in — applied AFTER the
run — produces the correct pass/fail.

Drives the REAL provider adapter (../adapter/discover.py + run.py) — no stubs —
and the REAL consumer stand-in (_consumer_disposition.py). Only the RAW violation
list crosses between them.

MIXED disposition (entity/contract = advisory, enum/naming = strict):
  clean -> provider RAW = []                          -> disposition PASS
  dirty -> provider RAW = 5 over 4 rule_ids           -> disposition FAIL
          * entity   (advisory): Score missing in Dart; Trophy missing in both
          * enum     (strict):   StatusEnum members differ (Dart has extra `pending`)
          * naming   (strict):   Player spelled PlayerEntity (py) vs PlayerModel (dart)
          * contract (advisory): Trophy implemented in no stack
      => verdict FAIL, 2 unsuppressed (enum + naming), 3 advisory (2 entity + 1 contract)

The crux (analogous to structured_logging's all_suppressed): the provider emits 5
RAW facts, yet only 2 drive the FAIL — the advisory routing of the 3 markerless
synthetic-location facts happens ENTIRELY downstream in the consumer.

Run:
    python3 official/atdd.workspace.python-pytest/e2e/prove_cross_language_consistency.py
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
IMPL_DIR = IMPLS_ROOT / "cross_language_consistency_detector"
EXPECTED_ID = "coder.boundaries.xlang-entity"

DISPOSITIONS = {
    "coder.boundaries.xlang-entity": "advisory",
    "coder.boundaries.xlang-enum": "strict",
    "coder.boundaries.xlang-naming": "strict",
    "coder.boundaries.xlang-contract": "advisory",
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
        print(f"    - [{v['rule_id']}] {v['file']}")
        print(f"        {v['evidence']}")


def _print_verdict(verdict: consumer.Verdict) -> None:
    print(f"  consumer disposition verdict: "
          f"{'PASS' if verdict.passed else 'FAIL'}  "
          f"(unsuppressed={len(verdict.unsuppressed)}, advisory={len(verdict.advisory)})")
    for rid, b in sorted(verdict.by_rule.items()):
        print(f"      {rid} [{b['disposition']}]: {b['unsuppressed']} unsuppressed")


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
        print("  PASS: full cross-stack parity -> no raw violations -> PASS")
    else:
        print("  FAIL: expected empty raw + PASS")
        ok = False

    _section("3. fixtures/dirty  -> expect RAW=5 over 4 rule_ids -> FAIL (2 unsuppressed)")
    dirty = _run_fixture("dirty")
    _print_raw(dirty)
    v_dirty = consumer.apply_disposition(dirty.violations, DISPOSITIONS)
    _print_verdict(v_dirty)
    dirty_rule_ids = {v["rule_id"] for v in dirty.violations}
    if (
        dirty.structured
        and len(dirty.violations) == 5
        and dirty_rule_ids == EXPECTED_RULE_IDS
        and not v_dirty.passed
        and len(v_dirty.unsuppressed) == 2
        and len(v_dirty.advisory) == 3
    ):
        print("  PASS: 5 raw over 4 rule_ids -> FAIL, 2 unsuppressed (enum+naming) / 3 advisory")
        print("        ^ advisory routing of 3 markerless synthetic facts decided DOWNSTREAM")
    else:
        print("  FAIL: expected 5 raw over 4 rule_ids -> FAIL with 2 unsuppressed / 3 advisory")
        ok = False

    _section("RESULT")
    print("  ALL PASS — mixed-disposition cross-language consistency proven end-to-end"
          if ok else "  FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
