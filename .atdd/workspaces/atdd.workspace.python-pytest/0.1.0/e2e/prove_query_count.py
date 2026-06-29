"""End-to-end proof: the python-pytest provider discovers + runs the STRICT
validator coder.refactor.nplus1 (disposition strict, severity 3), emits RAW
structured violations, and a SEPARATE consumer-side disposition stand-in produces
the correct pass/fail.

Drives the REAL provider adapter (../adapter/discover.py + run.py) — no stubs —
and the REAL consumer stand-in (_consumer_disposition.py). Strict -> any
violation FAILS; markers are ignored. (The `# noqa: N+1` marker is a DETECTION
exemption applied inside the detector, not a downstream disposition — the dirty
fixture's noqa'd call is simply never emitted.)

Proves, per fixture:
  clean -> provider RAW = []   -> disposition PASS
  dirty -> provider RAW = 1    -> disposition FAIL (1 unsuppressed; a 2nd noqa'd
                                  in-loop call is exempted at detection time)

Exit 0 only if every assertion holds. Run:
    python3 official/atdd.workspace.python-pytest/e2e/prove_query_count.py
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
IMPL_DIR = IMPLS_ROOT / "query_count_detector"
EXPECTED_ID = "coder.refactor.nplus1"
DISPOSITIONS = {EXPECTED_ID: "strict"}


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def _run_fixture(name: str) -> run_mod.RunResult:
    return run_mod.run_implementation(EXPECTED_ID, IMPL_DIR, scan_roots=[f"fixtures/{name}"])


def _print_raw(res: run_mod.RunResult) -> None:
    print(f"  structured={res.structured} ran={res.ran} passed={res.passed} "
          f"exit={res.exit_code}  RAW violations={len(res.violations)}")
    for v in res.violations:
        print(f"    - [{v['rule_id']}] {v['file']}:{v['line']}:{v['col']}  {v['evidence']}  "
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

    _section("3. fixtures/dirty  -> expect RAW=1 (noqa'd call exempted) -> disposition FAIL")
    dirty = _run_fixture("dirty")
    _print_raw(dirty)
    v_dirty = consumer.apply_disposition(dirty.violations, DISPOSITIONS)
    _print_verdict(v_dirty)
    if (
        dirty.structured
        and len(dirty.violations) == 1
        and {v["rule_id"] for v in dirty.violations} == {EXPECTED_ID}
        and "find_one" in dirty.violations[0]["evidence"]
        and not v_dirty.passed
        and len(v_dirty.unsuppressed) == 1
    ):
        print("  PASS: 1 raw (noqa'd in-loop call exempted at detection) -> strict FAIL")
    else:
        print("  FAIL: expected exactly 1 raw -> strict FAIL")
        ok = False

    _section("RESULT")
    print("  ALL PASS — strict N+1 (query_count) proof green"
          if ok else "  FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
