# URN: test:validate-conventions:variant-metadata-conformance:E011-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E011-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E011
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E011 — every implemented variant declares the required metadata fields"""
from __future__ import annotations

from pathlib import Path

import yaml

import ast
META = {"FAMILY","TEMPLATE","VARIANT","QUESTION","SELECTOR","TRAVERSAL","INVARIANT","AUTO_CAPTURE","FAILURE_EVIDENCE"}

def _variant_files(conventions_dir: Path):
    return [p for p in conventions_dir.glob("*/test_*.py") if p.parent.name != "tests"]

def test_variants_declare_metadata(conventions_dir: Path) -> None:
    variants = _variant_files(conventions_dir)
    assert variants, "no convention validator variants implemented yet"
    bad = []
    for p in variants:
        names = {n.id for node in ast.walk(ast.parse(p.read_text())) if isinstance(node, ast.Assign)
                 for n in node.targets if isinstance(n, ast.Name)}
        missing = META - names
        if missing or "LEGACY_PARITY_SOURCES" not in names:
            bad.append(f"{p.name}: missing {sorted(missing | ({'LEGACY_PARITY_SOURCES'} - names))}")
    assert not bad, f"variants with incomplete metadata: {bad}"


# --- #1979 -------------------------------------------------------------------
# `LEGACY_PARITY_SOURCES` is a PROVENANCE record of the legacy validator a variant
# replaced, so its target is *expected* to disappear once #1207 retires that
# validator. Asserting the path still exists would therefore be backwards: measured
# on the tree that introduced this check, it fails the 29 variants whose migration
# COMPLETED and passes all 63 whose legacy validator is still carrying the question.
#
# What must hold is the conservation law across the handoff: at every moment either
# the legacy validator still exists, or the variant itself executes the convention
# graph. Both gone is the only illegal state — it is a coverage deletion that leaves
# a green suite, and it is indistinguishable in `git log` from a correct retirement.

_GRAPH_FIXTURES = {"clean_convention_graph", "repo_root", "graph_rooted_at"}
_GRAPH_CALLS = {
    "load_composed_graph",
    "graph_rooted_at",
    "clone_graph",
    "mirror_file",
    "evaluate",
}


def _executes_graph(tree: ast.Module) -> bool:
    """True when any test in the module reaches the composed graph — by requesting a
    graph fixture, or by calling one of the loader//mutation helpers directly."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        if {a.arg for a in node.args.args} & _GRAPH_FIXTURES:
            return True
        for call in ast.walk(node):
            if isinstance(call, ast.Call):
                name = getattr(call.func, "id", None) or getattr(call.func, "attr", None)
                if name in _GRAPH_CALLS:
                    return True
    return False


def _legacy_parity_sources(tree: ast.Module) -> list[str] | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "LEGACY_PARITY_SOURCES" for t in node.targets
        ):
            try:
                return list(ast.literal_eval(node.value))
            except (ValueError, SyntaxError):
                return []
    return None


def test_retired_parity_source_implies_the_variant_executes(
    conventions_dir: Path, repo_root: Path
) -> None:
    """A variant whose every declared legacy parity source has been retired is the only
    thing left enforcing its question — so it must actually execute the graph."""
    orphaned = []
    for p in _variant_files(conventions_dir):
        tree = ast.parse(p.read_text())
        sources = _legacy_parity_sources(tree)
        if not sources:
            continue
        # A source may be a pytest node id (`path.py::test_name`); the file is the path.
        retired = [s for s in sources if not (repo_root / s.split("::")[0]).exists()]
        if len(retired) == len(sources) and not _executes_graph(tree):
            orphaned.append(f"{p.relative_to(conventions_dir)} (retired: {sorted(retired)})")
    assert not orphaned, (
        "variants whose legacy validator was retired but which assert nothing against "
        "the convention graph — the question they name is enforced by NOTHING. Either "
        "make the variant execute, or delete it if its subject is gone: "
        f"{orphaned}"
    )
