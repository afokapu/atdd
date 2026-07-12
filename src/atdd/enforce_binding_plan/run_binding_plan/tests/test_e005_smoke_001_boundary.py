# URN: test:enforce-binding-plan:run-binding-plan:E005-SMOKE-001-boundary
# Acceptance: acc:enforce-binding-plan:E005-SMOKE-001-boundary
# WMBT: wmbt:enforce-binding-plan:E005
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E005-SMOKE-001 — boundary discipline holds (V5).

The core ``atdd enforce`` verb must never import a provider module
(``atdd.workspace.*``); the provider CLI must never import core. This test
asserts the core side of that contract: an AST import-discipline guard over the
shipped core runner package finds no ``atdd.workspace.*`` import.

RED reason: the ``atdd enforce`` verb is absent (no runner is shipped yet), so
the verb-wired guard fails. When the runner ships, the AST scan becomes the
load-bearing guard that keeps core provider-agnostic (D-1).
"""
from __future__ import annotations

import ast

import pytest

from .conftest import VERB_ABSENT, repo_src

pytestmark = pytest.mark.smoke

# The shipped CORE runner package (excludes the vendored workspace providers).
_CORE_RUNNER_PKG = "atdd/enforce_binding_plan"


def _forbidden_workspace_imports(py_path) -> list[str]:
    """Return any `import atdd.workspace[.*]` statements found in *py_path*."""
    tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "atdd.workspace" or alias.name.startswith(
                    "atdd.workspace."
                ):
                    hits.append(f"{py_path}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "atdd.workspace" or mod.startswith("atdd.workspace."):
                hits.append(f"{py_path}:{node.lineno}: from {mod} import ...")
    return hits


def test_e005_smoke_001_core_runner_does_not_import_provider(run_enforce) -> None:
    # Verb-wired guard (load-bearing RED): the runner must be a real command.
    proc = run_enforce(["--help"], cwd=repo_src().parent)
    combined = proc.stdout + proc.stderr
    assert VERB_ABSENT not in combined, (
        "atdd enforce is not wired as a command — boundary cannot be verified"
    )

    # AST boundary guard: no core runner module may import a workspace provider.
    core_pkg = repo_src() / _CORE_RUNNER_PKG
    offenders: list[str] = []
    for py in core_pkg.rglob("*.py"):
        if "/tests/" in py.as_posix() or py.name == "conftest.py":
            continue  # the tests themselves are not shipped core runner code
        offenders.extend(_forbidden_workspace_imports(py))

    assert not offenders, (
        "core enforce runner imports a workspace provider (boundary violation):\n"
        + "\n".join(offenders)
    )
