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
