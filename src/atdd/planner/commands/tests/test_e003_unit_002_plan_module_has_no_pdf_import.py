# URN: test:define-plans:atdd-plan:E003-UNIT-002-plan-module-has-no-pdf-import
# Acceptance: acc:define-plans:E003-UNIT-002-plan-module-has-no-pdf-import
# WMBT: wmbt:define-plans:E003
# Phase: RED
# Layer: unit
# Assertion: structural
"""E003-UNIT-002 — plan.py module has no PDF extraction library import."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


def _collect_imported_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


def test_plan_module_has_no_pdf_import():
    plan_path = Path(__file__).parent.parent / "plan.py"
    assert plan_path.exists(), f"plan.py not found at {plan_path}"

    tree = ast.parse(plan_path.read_text())
    imports = _collect_imported_names(tree)

    pdf_imports = [n for n in imports if "pdf" in n.lower()]
    assert not pdf_imports, (
        f"plan.py must not import PDF libraries; found: {pdf_imports}"
    )
