# URN: test:drive-state-machine:record-agent-session-identity:D003-UNIT-004-no-core-path-reads-cmux
# Acceptance: acc:drive-state-machine:D003-UNIT-004-no-core-path-reads-cmux
# WMBT: wmbt:drive-state-machine:D003
# Phase: RED
# Harness: unit
# Layer: integration
"""D003-UNIT-004 — no core capture path reads or invokes a multiplexer.

Issue #1540, success criterion 10; #1480/#1483 are actively pruning cmux out of
core and this must not add to it.

The check is STRUCTURAL (ast), not a text grep, and that is deliberate: this
module's own docstring names cmux while explaining why it refuses to depend on
it, and a prose mention is not a code path. What is forbidden is an IMPORT of a
multiplexer module or an EXEC of a multiplexer binary. A regex would flag the
comment and miss `subprocess.run([resolved_name])` — the opposite of useful.

Fails until the capture modules exist and are clean (GREEN).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from atdd.state import agent_session

pytestmark = [pytest.mark.platform]

FORBIDDEN = ("cmux",)

# Every core module that participates in session capture. Kept explicit rather
# than globbed so that adding a capture path without listing it here is a
# reviewable omission, not a silent gap.
CAPTURE_MODULES = (agent_session,)


def _imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
    return names


def _string_literals(tree: ast.AST) -> set[str]:
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _docstrings(tree: ast.AST) -> set[str]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                out.add(doc)
    return out


@pytest.mark.parametrize("module", CAPTURE_MODULES, ids=lambda m: m.__name__)
def test_d003_unit_004_no_core_path_reads_cmux(module):
    tree = ast.parse(Path(module.__file__).read_text())

    for imported in _imported_names(tree):
        for bad in FORBIDDEN:
            assert bad not in imported.lower(), f"{module.__name__} imports {imported}"

    # string literals could smuggle in an exec target; docstrings are prose and
    # are explicitly allowed to discuss the constraint they enforce.
    executable_strings = _string_literals(tree) - _docstrings(tree)
    for literal in executable_strings:
        for bad in FORBIDDEN:
            assert bad not in literal.lower(), f"{module.__name__} references {literal!r}"


def test_d003_unit_004_guard_detects_a_planted_import():
    """The guard must actually fail on a violation — a guard that cannot fail is a stub."""
    planted = ast.parse("import cmux.client\n")
    assert any("cmux" in n for n in _imported_names(planted))

    planted_exec = ast.parse("subprocess.run(['cmux', 'events'])\n")
    literals = _string_literals(planted_exec) - _docstrings(planted_exec)
    assert any("cmux" in s for s in literals)
