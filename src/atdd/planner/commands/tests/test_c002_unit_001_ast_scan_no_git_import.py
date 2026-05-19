# URN: test:define-plans:atdd-plan:C002-UNIT-001-ast-scan-no-git-import
# Acceptance: acc:define-plans:C002-UNIT-001-ast-scan-no-git-import
# WMBT: wmbt:define-plans:C002
# Phase: RED
# Layer: unit
# Assertion: structural
"""C002-UNIT-001 — plan.py has no git or gh imports (AST scan)."""
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


def test_plan_module_has_no_git_import():
    plan_path = Path(__file__).parent.parent / "plan.py"
    assert plan_path.exists(), f"plan.py not found at {plan_path}"

    tree = ast.parse(plan_path.read_text())
    imports = _collect_imported_names(tree)

    forbidden = [
        n for n in imports
        if n == "git" or n.startswith("git.") or n == "gh" or n.startswith("gh.")
    ]
    assert not forbidden, (
        f"plan.py must not import git or gh modules; found: {forbidden}"
    )
