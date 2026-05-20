# URN: test:define-plans:atdd-plan:C002-UNIT-002-ast-scan-no-coach-import
# Acceptance: acc:define-plans:C002-UNIT-002-ast-scan-no-coach-import
# WMBT: wmbt:define-plans:C002
# Phase: RED
# Layer: unit
# Assertion: structural
"""C002-UNIT-002 — plan.py has no atdd.coach or atdd.*.commands.issue imports."""
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


def test_plan_module_has_no_coach_or_issue_import():
    plan_path = Path(__file__).parent.parent / "plan.py"
    assert plan_path.exists(), f"plan.py not found at {plan_path}"

    tree = ast.parse(plan_path.read_text())
    imports = _collect_imported_names(tree)

    forbidden = [
        n for n in imports
        if n.startswith("atdd.coach") or n.endswith(".commands.issue")
    ]
    assert not forbidden, (
        f"plan.py must not import atdd.coach or issue command modules; found: {forbidden}"
    )
