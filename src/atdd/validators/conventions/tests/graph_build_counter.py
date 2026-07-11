# URN: component:validate-conventions:tune-convention-suite:graph-build-counter:backend:domain
# Runtime: python
# Purpose: pytest plugin that counts real-root load_composed_graph() calls (#1414, E032).
"""Count how many times the CLEAN convention graph is composed in a pytest session.

Loaded with ``-p atdd.validators.conventions.tests.graph_build_counter`` by the E032
gate (``test_e032_single_graph_build.py``), which runs the read-only convention suite
in a subprocess and asserts the count is exactly 1.

Only builds rooted at the REAL repo root are counted. Fixture and fault-injection
suites compose throwaway graphs under ``tmp_path``; those are cheap, are not the
clean graph, and must not be conflated with it.

The count is written to the JSON file named by ``ATDD_GRAPH_BUILD_COUNT_FILE`` rather
than printed, so the gate never has to parse pytest's stdout.
"""
from __future__ import annotations

import importlib
import json
import os
import pkgutil
from pathlib import Path

from atdd.validators.conventions._support import graph_loader as _gl

_ORIGINAL = _gl.load_composed_graph


def _find_repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


_REPO_ROOT = _find_repo_root()
_STATS = {"builds": 0, "selected": 0}


def _counted(repo_root):
    if Path(repo_root).resolve() == _REPO_ROOT:
        _STATS["builds"] += 1
    return _ORIGINAL(repo_root)


_gl.load_composed_graph = _counted

# Modules that did `from ..graph_loader import load_composed_graph` hold their own
# reference to the original function; patching the defining module is not enough.
import atdd.validators.conventions as _conventions  # noqa: E402

for _mod_info in pkgutil.walk_packages(_conventions.__path__, _conventions.__name__ + "."):
    try:
        _module = importlib.import_module(_mod_info.name)
    except Exception:  # a module that cannot import cannot hold a stale reference
        continue
    if getattr(_module, "load_composed_graph", None) is _ORIGINAL:
        _module.load_composed_graph = _counted


def pytest_collection_finish(session):
    # NOT pytest_collection_modifyitems: `-k` deselection happens in the mark plugin's
    # own modifyitems hook, so an early hook sees every collected item, not the slice.
    _STATS["selected"] = len(session.items)


def pytest_sessionfinish(session, exitstatus):
    out = os.environ.get("ATDD_GRAPH_BUILD_COUNT_FILE")
    if out:
        Path(out).write_text(json.dumps(_STATS), encoding="utf-8")
