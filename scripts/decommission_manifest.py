#!/usr/bin/env python3
"""Deterministic decommission manifest for legacy validators (#1212).

SAFE, read-only. Emits — for every legacy validator referenced as a
``LEGACY_PARITY_SOURCES`` by a convention variant — the covering variant, whether
that variant actually EXECUTES (vs a RED-phase stub), and the rule node(s) whose
``implementation.ref``/``validator`` currently point at the legacy file (the
repoint targets for decommission coupling #2).

It does NOT delete anything. Output is the input to a per-file reconcile pass:
repoint rule -> convention variant, delete legacy test, drop the legacy-oracle
parity assertion.

Run:  PYTHONPATH=src python3 scripts/decommission_manifest.py
"""
from __future__ import annotations

import glob
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "src")
from atdd.validators.conventions._support.graph_loader import load_composed_graph


def _legacy_stem(path: str) -> str:
    return Path(path).name.removesuffix(".py")


def _ref_stem(ref: str | None) -> str | None:
    if not ref:
        return None
    return Path(ref.split("::", 1)[0]).name.removesuffix(".py")


def collect_variants():
    """legacy_path -> [ {variant_file, family, variant, phase, executes} ]"""
    out = defaultdict(list)
    for vf in sorted(glob.glob("src/atdd/validators/conventions/*/test_*.py")):
        txt = Path(vf).read_text(encoding="utf-8")
        m = re.search(r"LEGACY_PARITY_SOURCES\s*=\s*\[(.*?)\]", txt, re.S)
        if not m:
            continue
        sources = re.findall(r"['\"]([^'\"]+\.py)['\"]", m.group(1))
        phase = "RED" if re.search(r"#\s*Phase:\s*RED", txt) else "GREEN"
        fam = (re.search(r"FAMILY\s*=\s*['\"]([^'\"]+)", txt) or [None, Path(vf).parent.name])[1]
        var = (re.search(r"VARIANT\s*=\s*['\"]([^'\"]+)", txt) or [None, Path(vf).stem])[1]
        # "executes" = a real fault/parity/clean-baseline test on the live graph,
        # not merely the contract assert, and not a RED-phase stub.
        executes = phase == "GREEN" and bool(
            re.search(r"def test_.*(fault|parity|clean_baseline|catches|legacy)", txt)
        )
        for s in sources:
            out[s].append({"variant_file": vf, "family": fam, "variant": var,
                           "phase": phase, "executes": executes})
    return out


def main() -> int:
    variants = collect_variants()
    g = load_composed_graph(".")

    # rule nodes whose validator/implementation.ref points at a legacy file (by stem)
    rules_by_stem = defaultdict(list)
    for n in g.rules():
        st = _ref_stem(n.validator)
        if st:
            rules_by_stem[st].append((n.id, n.location))

    ready, not_ready, no_variant_link = [], [], []
    for legacy_path in sorted(variants):
        present = Path(legacy_path).exists()
        vs = variants[legacy_path]
        executes = any(v["executes"] for v in vs)
        repoint = rules_by_stem.get(_legacy_stem(legacy_path), [])
        row = {
            "legacy": legacy_path,
            "exists": present,
            "variants": [f"{v['family']}/{v['variant']} ({v['phase']})" for v in vs],
            "variant_executes": executes,
            "repoint_rules": [rid for rid, _ in repoint],
        }
        (ready if executes else not_ready).append(row)

    def dump(title, rows):
        print(f"\n## {title}  ({len(rows)})")
        for r in rows:
            print(f"- {r['legacy']}  [exists={r['exists']}]")
            print(f"    variant(s): {', '.join(r['variants'])}")
            print(f"    repoint rules ({len(r['repoint_rules'])}): "
                  f"{', '.join(r['repoint_rules']) or '(none — platform test / no rule binding)'}")

    print("# Decommission manifest (#1212) — READ-ONLY, nothing deleted")
    print(f"\nLegacy validators referenced by a convention variant: {len(variants)}")
    dump("DECOMMISSION-READY (variant executes — covered)", ready)
    dump("NOT READY (variant is RED-stub / contract-only — DO NOT DELETE)", not_ready)
    print("\n> Per ready file: repoint each rule's implementation.ref -> the convention "
          "variant, delete the legacy test, drop that variant's legacy-oracle assertion, "
          "CI-gate. Tier-2 (convention-only) / Tier-3 (function-level/hermetic) are "
          "separate decisions; cross-check verdicts in family-parity-report.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
