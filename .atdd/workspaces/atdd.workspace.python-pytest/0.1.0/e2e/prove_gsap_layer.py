"""End-to-end proof (Wave 1): the python-pytest provider discovers + runs the
STRICT GSAP layer-usage validator (coder.presentation.gsap-layer +
coder.presentation.gsap-commons), emits RAW structured multi-rule violations, and
a SEPARATE consumer-side disposition stand-in — applied AFTER the run — produces
the correct pass/fail.

Drives the REAL provider adapter (../adapter/discover.py + run.py) — no stubs —
and the REAL consumer stand-in (_consumer_disposition.py). The adapter and the
stand-in never import each other; only the RAW violation list crosses between.

Both rule_ids are `strict`, so the proof is the clean/dirty pair:
  clean -> provider RAW = []                 -> disposition PASS
  dirty -> provider RAW = 2 (2 rule_ids)     -> disposition FAIL (2 unsuppressed)
          (a GSAP import that sits INSIDE presentation/ produces nothing — proves
           the layer predicate, not a blanket gsap ban.)

Exit 0 only if every assertion holds. Run:
    python3 official/atdd.workspace.python-pytest/e2e/prove_gsap_layer.py
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
IMPL_DIR = IMPLS_ROOT / "gsap_layer_detector"
EXPECTED_ID = "coder.presentation.gsap-layer"

# Both rule_ids are strict — the disposition registry the consumer would build
# from the two convention nodes.
DISPOSITIONS = {
    "coder.presentation.gsap-layer": "strict",
    "coder.presentation.gsap-commons": "strict",
}


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
        print("  PASS: clean (gsap only in presentation) -> no raw violations -> PASS")
    else:
        print("  FAIL: expected empty raw + PASS")
        ok = False

    _section("3. fixtures/dirty  -> expect RAW=2 over 2 rule_ids -> disposition FAIL")
    dirty = _run_fixture("dirty")
    _print_raw(dirty)
    v_dirty = consumer.apply_disposition(dirty.violations, DISPOSITIONS)
    dirty_rule_ids = {v["rule_id"] for v in dirty.violations}
    if (
        dirty.structured
        and len(dirty.violations) == 2
        and dirty_rule_ids == {"coder.presentation.gsap-layer", "coder.presentation.gsap-commons"}
        and not v_dirty.passed
        and len(v_dirty.unsuppressed) == 2
    ):
        print("  PASS: 2 raw (gsap-layer + gsap-commons) -> FAIL, 2 unsuppressed")
        print("        ^ the presentation-layer GSAP import was correctly NOT flagged")
    else:
        print("  FAIL: expected 2 raw over 2 rule_ids -> strict FAIL")
        ok = False

    _section("RESULT")
    print("  ALL PASS — strict GSAP layer-usage proven end-to-end"
          if ok else "  FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
