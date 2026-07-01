#!/usr/bin/env python3
"""Deterministic decommission manifest + pre-flight classifier for legacy validators (#1212, #1263).

SAFE, read-only. Two jobs:

1. Manifest (#1212) — emit, for every legacy validator referenced as a
   ``LEGACY_PARITY_SOURCES`` by a convention variant, the covering variant, whether
   that variant actually EXECUTES (vs a RED-phase stub), and the rule node(s) whose
   ``implementation.ref``/``validator`` currently point at the legacy file.

2. Pre-flight classifier (#1263) — for every decommission-READY candidate, label it
   **PLATFORM** (clean delete), **RULE-BOUND** (a rule's ``implementation.ref`` must be
   repointed to the convention variant), and/or **ACCEPTANCE-ANCHORED** (the legacy test
   carries a ``# Acceptance:`` header whose plan acceptance must be retired/re-anchored).
   It also surfaces the current ``legacy-validator-map.yaml`` parity_status + whether the
   recorded ``proposed_target_path`` resolves, and emits the exact required steps. This is
   the pre-flight that prevents the two batch failures:
     - batch 1 (#1255): orphaned acceptance -> ``validator-binding-must-be-bidirectional``
     - batch 2 (#1260): stale/un-repointed map target -> ``test_no_unsafe_legacy_deletion``

It does NOT delete anything. Output is the input to a per-file reconcile pass.

Run:  PYTHONPATH=src python3 scripts/decommission_manifest.py
"""
from __future__ import annotations

import glob
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, "src")
from atdd.validators.conventions._support.graph_loader import load_composed_graph

# Mirror of the SAFE set enforced by the CI catch
# src/atdd/validators/conventions/tests/test_y001_no_unsafe_deletion.py.
# A legacy file may only be DELETED when its map entry's parity_status is one of
# these AND its proposed_target_path resolves to an existing convention variant.
SAFE_STATUSES = {"direct", "split", "merged", "superseded"}

CATCH_DELETION = "test_no_unsafe_legacy_deletion"
CATCH_BINDING = "tester.acceptance-violation.validator-binding-must-be-bidirectional"


def _legacy_stem(path: str) -> str:
    return Path(path).name.removesuffix(".py")


def _ref_stem(ref: str | None) -> str | None:
    if not ref:
        return None
    return Path(ref.split("::", 1)[0]).name.removesuffix(".py")


def collect_variants(root: Path):
    """legacy_path -> [ {variant_file, family, variant, phase, executes} ]"""
    out = defaultdict(list)
    for vf in sorted(glob.glob(str(root / "src/atdd/validators/conventions/*/test_*.py"))):
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


def load_legacy_map(root: Path) -> dict:
    """legacy_path -> entry dict from docs/validator-parity/legacy-validator-map.yaml."""
    mp = root / "docs" / "validator-parity" / "legacy-validator-map.yaml"
    if not mp.exists():
        return {}
    doc = yaml.safe_load(mp.read_text(encoding="utf-8")) or {}
    return {e.get("legacy_path"): e for e in (doc.get("entries") or []) if e.get("legacy_path")}


def read_acceptances(path: Path) -> list[str]:
    """`# Acceptance: acc:...` URNs declared by a legacy test (empty if absent)."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*#\s*Acceptance:\s*(\S+)", line)
        if m:
            out.append(m.group(1))
        elif line.strip() and not line.lstrip().startswith("#"):
            break  # header block ends at first non-comment code line
    return out


def classify(repo_root: str | Path = ".") -> list[dict]:
    """Pre-flight classification of every decommission-READY legacy validator.

    READ-ONLY. Returns one row per ready candidate with its label set, the current
    legacy-validator-map.yaml parity_status + target resolvability, and the exact
    required retirement steps. Importable so a SMOKE test can assert the partition.
    """
    root = Path(repo_root)
    variants = collect_variants(root)
    g = load_composed_graph(str(root))

    rules_by_stem = defaultdict(list)
    for n in g.rules():
        st = _ref_stem(n.validator)
        if st:
            rules_by_stem[st].append(n.id)

    legacy_map = load_legacy_map(root)

    rows = []
    for legacy_path in sorted(variants):
        vs = variants[legacy_path]
        if not any(v["executes"] for v in vs):
            continue  # NOT READY (RED-stub / contract-only) — out of scope

        entry = legacy_map.get(legacy_path, {})
        parity_status = entry.get("parity_status")
        target = entry.get("proposed_target_path")
        target_exists = bool(target) and (root / target).exists()
        map_rule_ids = list(entry.get("legacy_rule_ids") or [])
        repoint_rules = sorted(set(rules_by_stem.get(_legacy_stem(legacy_path), [])) | set(map_rule_ids))
        acceptances = read_acceptances(root / legacy_path)

        rule_bound = bool(repoint_rules)
        acceptance_anchored = bool(acceptances)
        platform = not rule_bound and not acceptance_anchored

        labels = []
        if platform:
            labels.append("PLATFORM")
        else:
            if rule_bound:
                labels.append("RULE-BOUND")
            if acceptance_anchored:
                labels.append("ACCEPTANCE-ANCHORED")

        map_status_ok = parity_status in SAFE_STATUSES and target_exists

        steps = []
        if rule_bound:
            steps.append(
                f"REPOINT {len(repoint_rules)} rule(s) implementation.ref -> the convention "
                f"variant nodeid ({', '.join(repoint_rules)}). [catch: {CATCH_DELETION}]"
            )
        if acceptance_anchored:
            steps.append(
                f"ACCEPTANCE: retire or re-anchor {len(acceptances)} plan acceptance(s) "
                f"({', '.join(acceptances)}) — coverage now lives in the variant. "
                f"[catch: {CATCH_BINDING}]"
            )
        steps.append("DELETE the legacy validator test file.")
        steps.append("DROP the variant's legacy-oracle (subprocess pytest) assertion.")
        if not map_status_ok:
            steps.append(
                f"FIX legacy-validator-map.yaml entry BEFORE deletion: parity_status="
                f"{parity_status!r} (need one of {sorted(SAFE_STATUSES)}), "
                f"proposed_target_path={target!r} (resolves={target_exists}). "
                f"[catch: {CATCH_DELETION}]"
            )

        rows.append({
            "legacy": legacy_path,
            "exists": (root / legacy_path).exists(),
            "labels": labels,
            "variants": [f"{v['family']}/{v['variant']} ({v['phase']})" for v in vs],
            "parity_status": parity_status,
            "proposed_target_path": target,
            "target_exists": target_exists,
            "map_status_ok": map_status_ok,
            "repoint_rules": repoint_rules,
            "acceptances": acceptances,
            "required_steps": steps,
        })
    return rows


def main() -> int:
    root = Path(".")
    rows = classify(root)

    print("# Decommission pre-flight (#1212/#1263) — READ-ONLY, nothing deleted\n")
    print(f"Decommission-READY candidates (variant executes — covered): {len(rows)}")

    def tally(label):
        return sum(1 for r in rows if label in r["labels"])

    print(f"  PLATFORM (clean delete):          {tally('PLATFORM')}")
    print(f"  RULE-BOUND (needs repoint):        {tally('RULE-BOUND')}")
    print(f"  ACCEPTANCE-ANCHORED (acc handling):{tally('ACCEPTANCE-ANCHORED')}")
    unsafe = [r for r in rows if not r["map_status_ok"]]
    print(f"  ⚠ map entry NOT delete-ready (would trip {CATCH_DELETION}): {len(unsafe)}")

    print("\n## Per-candidate classification\n")
    for r in rows:
        print(f"- {r['legacy']}  [exists={r['exists']}]")
        print(f"    labels: {' + '.join(r['labels'])}")
        print(f"    variant(s): {', '.join(r['variants'])}")
        print(f"    map status: parity_status={r['parity_status']!r} "
              f"target={r['proposed_target_path']!r} resolves={r['target_exists']} "
              f"-> delete-ready={r['map_status_ok']}")
        if r["repoint_rules"]:
            print(f"    repoint rules ({len(r['repoint_rules'])}): {', '.join(r['repoint_rules'])}")
        if r["acceptances"]:
            print(f"    anchored acceptances ({len(r['acceptances'])}): {', '.join(r['acceptances'])}")
        print("    required steps:")
        for i, s in enumerate(r["required_steps"], 1):
            print(f"      {i}. {s}")

    print("\n> Canonical runbook: docs/validator-parity/decommission-runbook.md "
          "(superseded the #1207 batch-1 addendum). The 4 steps + 2 CI catches are listed there. "
          "Tier-1 only; verdict authority = docs/validator-parity/family-parity-report.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
