#!/usr/bin/env python3
"""Assertion-accurate decommission readiness for legacy validators (#1207).

SAFE, read-only. Supersedes the FILE-granularity view of
``decommission_manifest.py`` (which marks a legacy file "ready" if ONE of its
assertions has a covering variant, missing that another assertion in the SAME
file is the sole enforcer of a migrated rule with no mirror — see #1207 / the
``planner.train.registry`` case).

The decommission unit is the ASSERTION (a top-level ``test_*`` function), not the
file. For every legacy validator file referenced by a convention variant, this
enumerates each test function and classifies it:

  covered      — a convention variant proves parity against THIS exact nodeid
                 (variant `_LEGACY_NODEID`/`LEGACY_NODEID == path::func`) and the
                 variant executes (not a RED stub).
  blocked      — a migrated rule's `implementation.ref`/`validator` binds this
                 function, but NO convention variant mirrors it. Deleting the file
                 would orphan that rule. Build the variant first (NOT doc-only).
  unbound      — no declared rule binds this function (ad-hoc structural check).
                 Out of convention-graph scope; deletable but record the drop.

A legacy file is ``file_ready`` only when EVERY function is covered or unbound
(no blocked). Catch-matrix coupling (a function used as a `legacy_target` oracle
in ``_support/catch_matrix.py``) is reported as a required follow-up edit, not a
blocker.

Run:  PYTHONPATH=src python3 scripts/decommission_assertions.py
"""
from __future__ import annotations

import ast
import glob
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "src")
from atdd.validators.conventions._support.graph_loader import load_composed_graph

_CONV_GLOB = "src/atdd/validators/conventions/*/test_*.py"
_CATCH_MATRIX = "src/atdd/validators/conventions/_support/catch_matrix.py"
_NODEID_RE = re.compile(r"([A-Za-z0-9_./-]+\.py)::([A-Za-z0-9_]+)")


def _ast_string_constants(path: Path):
    """All string constants in a module. Python's parser auto-joins implicit
    adjacent-literal concatenation (``"a.py" "::b"`` -> ``"a.py::b"``), so legacy
    nodeids split across lines are recovered here where a raw regex would miss them."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return []
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def _nodeids_in(path: Path):
    out = set()
    for s in _ast_string_constants(path):
        for m in _NODEID_RE.finditer(s):
            out.add(f"{m.group(1)}::{m.group(2)}")
    return out


def variant_coverage():
    """Map precise legacy nodeid 'path::func' -> {variant, executes} (the nodeids a
    variant actually proves parity against). Scans BOTH the variant file and its
    family ``_parity*.py`` helpers, since some families (e.g. acyclicity) keep the
    legacy nodeid in a shared helper, not a per-variant constant."""
    cover = {}
    # family-shared _parity helpers: any nodeid here is a real parity target.
    for pf in glob.glob("src/atdd/validators/conventions/*/_parity*.py"):
        fam = Path(pf).parent.name
        for nodeid in _nodeids_in(Path(pf)):
            cover.setdefault(nodeid, {"variant": f"{fam}/_parity", "executes": True, "file": pf})
    for vf in sorted(glob.glob(_CONV_GLOB)):
        txt = Path(vf).read_text(encoding="utf-8")
        phase = "RED" if re.search(r"#\s*Phase:\s*RED", txt) else "GREEN"
        executes = phase == "GREEN" and bool(
            re.search(r"def test_.*(fault|parity|clean_baseline|catches|legacy)", txt)
        )
        fam = (re.search(r"FAMILY\s*=\s*['\"]([^'\"]+)", txt) or [None, Path(vf).parent.name])[1]
        var = (re.search(r"VARIANT\s*=\s*['\"]([^'\"]+)", txt) or [None, Path(vf).stem])[1]
        for nodeid in _nodeids_in(Path(vf)):
            # variant-declared nodeid wins (carries the real executes flag + name)
            cover[nodeid] = {"variant": f"{fam}/{var}", "executes": executes, "file": vf}
    return cover


def rule_bindings(graph):
    """Two indexes from the composed graph's rule nodes:
        by_func:  bare function name           -> [(rule_id, location)]
        by_modfn: (file_stem, function_name)   -> [(rule_id, location)]
    Covers both single-node `implementation.ref` (bare func) and old-format
    `validator: "<module>::<func>"`."""
    by_func = defaultdict(list)
    by_modfn = defaultdict(list)
    for n in graph.rules():
        ref = n.validator
        if not ref:
            continue
        if "::" in ref:
            mod, fn = ref.split("::", 1)
            stem = Path(mod).name.removesuffix(".py")
            by_modfn[(stem, fn)].append((n.id, n.location))
        else:
            # bare token: a function name (e.g. single-node implementation.ref)
            # or a free-form spec string — index the function-name candidate.
            tok = ref.strip()
            cand = re.search(r"([A-Za-z_][A-Za-z0-9_]*)", tok)
            if cand:
                by_func[cand.group(1)].append((n.id, n.location))
    return by_func, by_modfn


def catch_matrix_targets():
    p = Path(_CATCH_MATRIX)
    if not p.exists():
        return set()
    return {f"{m.group(1)}::{m.group(2)}"
            for m in _NODEID_RE.finditer(p.read_text(encoding="utf-8"))}


def legacy_files(cover_keys):
    """Legacy files referenced by a variant LEGACY_PARITY_SOURCES (decommission
    candidate scope), same as decommission_manifest.py."""
    files = set()
    for vf in glob.glob(_CONV_GLOB):
        txt = Path(vf).read_text(encoding="utf-8")
        m = re.search(r"LEGACY_PARITY_SOURCES\s*=\s*\[(.*?)\]", txt, re.S)
        if m:
            files.update(re.findall(r"['\"]([^'\"]+\.py)['\"]", m.group(1)))
    return sorted(files)


def test_functions(path: Path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return []
    return [node.name for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]


def main() -> int:
    graph = load_composed_graph(".")
    cover = variant_coverage()
    by_func, by_modfn = rule_bindings(graph)
    cm_targets = catch_matrix_targets()

    files = legacy_files(set(cover))
    ready, blocked_files, unbound_only = [], [], []

    for lf in files:
        p = Path(lf)
        if not p.exists():
            continue
        stem = p.name.removesuffix(".py")
        rows, statuses = [], []
        for fn in test_functions(p):
            nodeid = f"{lf}::{fn}"
            covered = nodeid in cover and cover[nodeid]["executes"]
            bound = by_func.get(fn, []) + by_modfn.get((stem, fn), [])
            if covered:
                status = "covered"
            elif bound:
                status = "blocked"
            else:
                status = "unbound"
            statuses.append(status)
            rows.append({
                "fn": fn, "status": status,
                "variant": cover.get(nodeid, {}).get("variant"),
                "rules": [rid for rid, _ in bound],
                "in_catch_matrix": nodeid in cm_targets,
            })
        file_ready = bool(rows) and all(s in ("covered", "unbound") for s in statuses)
        rec = {"file": lf, "rows": rows, "file_ready": file_ready,
               "blocked": [r for r in rows if r["status"] == "blocked"],
               "cm": [r["fn"] for r in rows if r["in_catch_matrix"]]}
        if any(r["status"] == "blocked" for r in rows):
            blocked_files.append(rec)
        elif all(r["status"] == "unbound" for r in rows):
            unbound_only.append(rec)
        else:
            ready.append(rec)

    def dump(title, recs):
        print(f"\n## {title}  ({len(recs)})")
        for r in recs:
            cm = f"  ⚠ catch_matrix oracle: {', '.join(r['cm'])}" if r["cm"] else ""
            print(f"\n- {r['file']}  file_ready={r['file_ready']}{cm}")
            for row in r["rows"]:
                tag = {"covered": "✓", "blocked": "✗ BLOCKED", "unbound": "·"}[row["status"]]
                extra = f" -> {row['variant']}" if row["variant"] else ""
                rules = f"  rules={row['rules']}" if row["rules"] else ""
                print(f"    [{tag}] {row['fn']}{extra}{rules}")

    print("# Assertion-accurate decommission readiness (#1207) — READ-ONLY")
    print(f"\nLegacy candidate files: {len(files)} | "
          f"variant-covered nodeids: {len(cover)} | catch_matrix oracle nodeids: {len(cm_targets)}")
    dump("FILE-READY (every assertion covered or unbound — deletable)", ready)
    dump("BLOCKED (>=1 migrated-rule assertion with NO covering variant — build variant first)", blocked_files)
    dump("UNBOUND-ONLY (no rule bindings; structural checks — deletable, record coverage drop)", unbound_only)
    n_blocked_assertions = sum(len(r["blocked"]) for r in blocked_files)
    print(f"\nSUMMARY: file_ready={len(ready)}  blocked_files={len(blocked_files)} "
          f"({n_blocked_assertions} blocked assertions)  unbound_only_files={len(unbound_only)}")
    print("A file is deletable only when EVERY assertion is covered or unbound. "
          "Catch_matrix oracle functions (⚠) require a corpus edit in the same change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
