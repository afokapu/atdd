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

import gc
import shutil
from pathlib import Path

import pytest

from atdd.validators.conventions._support.graph_loader import (
    ConventionGraph,
    load_composed_graph,
)
from atdd.validators.conventions._support.mutation_guard import (  # noqa: F401
    assign_default_class,
    mutation_class_guard,
)

_CONVENTIONS_DIR = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """#1418 — every convention test lands in exactly one mutation class, so the CI split
    `-m "not convention_filesystem_mutation"` / `-m "convention_filesystem_mutation"` is a
    true partition and no test can fall through both filters."""
    assign_default_class(items, _CONVENTIONS_DIR)


def _find_repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


# Synthetic fault-probe artifacts the remaining LOADER fault tests create on the real
# tree (their evaluators re-scan disk, so the fault must be a real file). All are
# untracked and could NEVER legitimately exist in the tree. A SIGKILLed run leaves them
# behind; because the graph loader and the disk-rescanning baselines (`no_orphan`,
# `wmbt_has_smoke`, coherence) then observe them, a stale probe poisons the very
# `-k baseline` read-only subset the E032 gate spawns — which deselects the fault tests,
# so it can never clean up after itself. Swept once per session BEFORE the graph is
# composed. Keep in sync with the fault tests that write these (grep the file names).
_SYNTHETIC_RESIDUE_FILES = (
    "src/atdd/planner/conventions/nodes/_tmp_coverage_orphan_probe.convention.yaml",
    "plan/validate_conventions/E996.yaml",
    "src/atdd/_atdd1212_stale_suppression_parity.py",
)
_SYNTHETIC_RESIDUE_DIRS = (
    "plan/zz_archetype_probe",
    "src/atdd/planner/zz_archetype_probe",
)
_SYNTHETIC_RESIDUE_GLOBS = ("src/atdd/*/_boundary_fault_injection.py",)


def _sweep_synthetic_fault_residue(root: Path) -> None:
    for rel in _SYNTHETIC_RESIDUE_FILES:
        (root / rel).unlink(missing_ok=True)
    for pattern in _SYNTHETIC_RESIDUE_GLOBS:
        for p in root.glob(pattern):
            p.unlink(missing_ok=True)
    for rel in _SYNTHETIC_RESIDUE_DIRS:
        shutil.rmtree(root / rel, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def _clean_fault_residue() -> None:
    """Clear synthetic fault-probe residue from a prior interrupted run before anything
    reads the tree, so the session graph and every disk-rescanning baseline start clean
    regardless of how a previous run died."""
    _sweep_synthetic_fault_residue(_find_repo_root())


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return _find_repo_root()


@pytest.fixture(scope="session")
def clean_convention_graph(_clean_fault_residue) -> ConventionGraph:
    # Resolves the root directly instead of requesting the `repo_root` fixture: the
    # `tests/` and `presence/` conftests override `repo_root` at function scope, and a
    # session-scoped fixture may not depend on a function-scoped one (ScopeMismatch).
    # Depends on `_clean_fault_residue` so the graph is never composed over stale residue.
    graph = load_composed_graph(_find_repo_root())

    # Retaining a whole graph for the session makes every later gen-2 collection walk
    # its tens of thousands of Nodes, which taxes the fault-injection tests that still
    # compose their own graph: measured, holding it pushed the mean build from 2.78s to
    # 3.42s and gave back only 35s of the ~90s the saved builds should have yielded.
    # gc.freeze() moves everything currently alive into the permanent generation, so the
    # collector stops traversing it. Mean build 2.62s; suite 333s -> 260s.
    gc.freeze()
    return graph
