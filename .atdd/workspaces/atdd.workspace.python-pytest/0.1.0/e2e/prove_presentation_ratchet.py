"""End-to-end proof (Wave 1): the python-pytest provider discovers + runs the
ADVISORY-GATE presentation-ratchet validator (coder.refactor.coach-ratchet-pres),
emits RAW structured reductions, and a SEPARATE consumer-side disposition gate —
applied AFTER the run — produces the correct pass/fail via SMOKE EVIDENCE.

This validator does NOT cleanly fit the strict / suppress-and-clean trichotomy:
its disposition is advisory + an EVIDENCE GATE. Smoke evidence plays the role the
inline `# atdd:suppress(...)` marker plays for `coder.logging.structured` — it is
an external absorber the provider never reads. So this proof uses a LOCAL gate
(not the shared _consumer_disposition) that mirrors core ``has_smoke_evidence``:
a reduction is absorbed iff `.atdd/smoke-evidence/<issue>.yaml` exists for it.

  clean     -> provider RAW = []              -> gate PASS (nothing to verify)
  dirty     -> provider RAW = 1, NO evidence  -> gate FAIL (1 ungated reduction)
  evidenced -> provider RAW = 1 (NON-EMPTY), evidence present -> gate PASS    <-- crux
              (same reduction as dirty; the verdict flips ENTIRELY downstream.)

The adapter never reads smoke evidence; only the RAW reduction list crosses the
boundary, plus the consumer's own filesystem check of the mounted scan root.

Run:
    python3 official/atdd.workspace.python-pytest/e2e/prove_presentation_ratchet.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_WS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_WS / "adapter"))

import discover as discover_mod  # noqa: E402
import run as run_mod  # noqa: E402

IMPLS_ROOT = _WS / "implementations"
IMPL_DIR = IMPLS_ROOT / "presentation_ratchet_detector"
EXPECTED_ID = "coder.refactor.coach-ratchet-pres"


# ── consumer-side advisory gate (mirrors core has_smoke_evidence) ─────────────
# Lives OUTSIDE the provider. The adapter never imports this; it only reads the
# RAW reduction list + the consumer's own evidence directory under the scan root.

def _has_smoke_evidence(scan_root: Path, issue) -> bool:
    return (scan_root / ".atdd" / "smoke-evidence" / f"{issue}.yaml").is_file()


def apply_evidence_gate(violations: list[dict], scan_root: Path):
    """advisory + smoke-evidence gate: a reduction is absorbed iff its issue has
    recorded smoke evidence. PASS iff no ungated reductions remain."""
    gated: list[dict] = []
    absorbed: list[dict] = []
    for v in violations:
        if _has_smoke_evidence(scan_root, v.get("issue")):
            absorbed.append(v)
        else:
            gated.append(v)
    return (len(gated) == 0), gated, absorbed


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def _run_fixture(name: str) -> run_mod.RunResult:
    return run_mod.run_implementation(EXPECTED_ID, IMPL_DIR, scan_roots=[f"fixtures/{name}"])


def _print_raw(res: run_mod.RunResult) -> None:
    print(f"  structured={res.structured} ran={res.ran} passed={res.passed} "
          f"exit={res.exit_code}  RAW violations={len(res.violations)}")
    for v in res.violations:
        print(f"    - [{v['rule_id']}] {v['file']} (issue={v.get('issue')})")
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

    _section("2. fixtures/clean  -> expect RAW=[] -> gate PASS")
    clean = _run_fixture("clean")
    _print_raw(clean)
    passed, gated, _ = apply_evidence_gate(clean.violations, IMPL_DIR / "fixtures" / "clean")
    if clean.structured and clean.violations == [] and passed:
        print("  PASS: no >20% presentation reduction -> no raw -> PASS")
    else:
        print("  FAIL: expected empty raw + PASS")
        ok = False

    _section("3. fixtures/dirty  -> expect RAW=1, NO evidence -> gate FAIL")
    dirty = _run_fixture("dirty")
    _print_raw(dirty)
    passed, gated, absorbed = apply_evidence_gate(dirty.violations, IMPL_DIR / "fixtures" / "dirty")
    print(f"  gate verdict: {'PASS' if passed else 'FAIL'}  "
          f"(ungated={len(gated)}, absorbed={len(absorbed)})")
    if (
        dirty.structured
        and len(dirty.violations) == 1
        and dirty.violations[0]["rule_id"] == EXPECTED_ID
        and not passed
        and len(gated) == 1
    ):
        print("  PASS: 1 raw reduction, no smoke evidence -> FAIL (1 ungated)")
    else:
        print("  FAIL: expected 1 raw -> gate FAIL")
        ok = False

    _section("4. fixtures/evidenced  -> expect RAW NON-EMPTY, evidence present -> gate PASS")
    evid = _run_fixture("evidenced")
    _print_raw(evid)
    passed, gated, absorbed = apply_evidence_gate(evid.violations, IMPL_DIR / "fixtures" / "evidenced")
    print(f"  gate verdict: {'PASS' if passed else 'FAIL'}  "
          f"(ungated={len(gated)}, absorbed={len(absorbed)})")
    if (
        evid.structured
        and len(evid.violations) == 1          # provider emits RAW non-empty
        and passed                              # ...yet the verdict is PASS
        and len(absorbed) == 1
        and len(gated) == 0
    ):
        print("  PASS: provider emits 1 RAW, consumer absorbs via smoke evidence -> PASS")
        print("        ^ disposition decided ENTIRELY downstream — separability proven")
    else:
        print("  FAIL: expected RAW non-empty + verdict PASS via smoke evidence")
        ok = False

    _section("RESULT")
    print("  ALL PASS — advisory-gate ratchet proven; smoke-evidence gate cleanly separable"
          if ok else "  FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
