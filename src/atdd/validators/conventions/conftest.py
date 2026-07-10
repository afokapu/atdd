# URN: component:validate-conventions:tune-convention-suite:session-graph-fixture:backend:domain
# Runtime: python
# Purpose: Session-scoped clean convention graph shared by every family (#1414, E032).
"""Fixtures shared by all 13 convention families.

``load_composed_graph()`` walks ``plan/`` and every ``*.convention.yaml`` under
``src/atdd/``, costing ~2-3s a call. The read-only baseline and contract tests all
evaluate their family template against the same *unmodified* repo, so the graph is
composed once per session here and reused.

``clean_convention_graph`` is for READ-ONLY tests only. A fault-injection test mutates
the tree and must re-read it — both to see its own injection and to prove the revert
left no residue — so it keeps calling ``load_composed_graph(root)`` directly. Handing
it the session graph would make those assertions vacuous.

For the same reason ``load_composed_graph`` itself is deliberately NOT memoized: it
reads mutable files, and a process-wide cache would silently serve a stale graph to the
fault-injection suites.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.validators.conventions._support.graph_loader import (
    ConventionGraph,
    load_composed_graph,
)


def _find_repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return _find_repo_root()


@pytest.fixture(scope="session")
def clean_convention_graph() -> ConventionGraph:
    # Resolves the root directly instead of requesting the `repo_root` fixture: the
    # `tests/` and `presence/` conftests override `repo_root` at function scope, and a
    # session-scoped fixture may not depend on a function-scoped one (ScopeMismatch).
    return load_composed_graph(_find_repo_root())
