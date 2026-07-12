# URN: test:validate-conventions:anti-regression-gate:E015-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E015-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E015
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E015 — no convention-graph validator is placed under a legacy persona validator folder"""
from __future__ import annotations

from pathlib import Path

import yaml

import ast
PERSONA_ROOTS = ["src/atdd/planner/validators","src/atdd/tester/validators","src/atdd/coder/validators","src/atdd/coach/validators"]
META_MARKERS = {"FAMILY","TEMPLATE","VARIANT"}

def test_no_convention_variant_under_persona_folders(repo_root: Path) -> None:
    offenders = []
    for root in PERSONA_ROOTS:
        for p in (repo_root / root).glob("*.py"):
            try:
                names = {n.id for node in ast.walk(ast.parse(p.read_text())) if isinstance(node, ast.Assign)
                         for n in node.targets if isinstance(n, ast.Name)}
            except SyntaxError:
                continue
            if META_MARKERS <= names:
                offenders.append(f"{root}/{p.name}")
    assert not offenders, f"convention-graph validators misplaced under persona folders: {offenders}"
