# URN: test:govern-lifecycle:fix-issue-reconcile-unbound-local-shadowed-import:E054-UNIT-002-no-function-local-issuemanager-import-shadows-module-global
# Acceptance: acc:govern-lifecycle:E054-UNIT-002-no-function-local-issuemanager-import-shadows-module-global
# WMBT: wmbt:govern-lifecycle:E054
# Phase: RED
# Harness: unit
# Assertion: structural
# Layer: backend
"""E054-UNIT-002 — no function-local import inside main() binds the name IssueManager.

Structural contract: ``src/atdd/cli.py`` is AST-parsed, the ``main()`` FunctionDef
is located, and every Import / ImportFrom node within its body is inspected. Zero of
them may bind the name ``IssueManager`` (a function-local binding makes the name
local for the entire function and shadows the module global, which is the root cause
of the reconcile UnboundLocalError). The module-level
``from atdd.coach.commands.issue import IssueManager`` must remain.

RED now: two function-local imports inside ``main()`` (the ``atdd issue <slug>
--dry-run`` branch and the ``manifest backfill`` branch) bind ``IssueManager``.
GREEN: both are removed, so the only binding left is the module-level import.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _cli_source_path() -> Path:
    # src/atdd/coach/commands/tests/<this>  → parents[4] == src
    return Path(__file__).resolve().parents[4] / "atdd" / "cli.py"


def _imported_names(node: ast.stmt) -> list[str]:
    """Names a single Import / ImportFrom statement binds in local scope."""
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return [alias.asname or alias.name for alias in node.names]
    return []


def _find_main(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node
    raise AssertionError("could not locate main() FunctionDef in cli.py")


def test_main_has_no_function_local_issuemanager_import() -> None:
    source = _cli_source_path().read_text(encoding="utf-8")
    tree = ast.parse(source)
    main_fn = _find_main(tree)

    offending: list[int] = []
    for node in ast.walk(main_fn):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if "IssueManager" in _imported_names(node):
                offending.append(getattr(node, "lineno", -1))

    assert offending == [], (
        "function-local import(s) of IssueManager inside main() shadow the module "
        f"global at line(s) {offending}; remove them so IssueManager resolves to the "
        "module-level import on every dispatch path"
    )


def test_module_level_issuemanager_import_remains() -> None:
    source = _cli_source_path().read_text(encoding="utf-8")
    tree = ast.parse(source)

    found_module_level = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "atdd.coach.commands.issue"
        and "IssueManager" in _imported_names(node)
        for node in tree.body
    )

    assert found_module_level, (
        "module-level `from atdd.coach.commands.issue import IssueManager` must "
        "remain at cli.py module scope"
    )
