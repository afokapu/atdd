"""Canonical valid/invalid graph fragments for the `boundary` family (#1206, #1212).

The `boundary/allowed_boundary_crossing` template constrains the on-disk
module-import graph, so a fragment is a tiny REAL repo (a wagon manifest under
``plan/`` + a source tree under ``src/atdd/``) materialized onto a filesystem and
loaded through ``load_composed_graph`` into genuine ``ConventionGraph`` /``Node``
objects. Fixtures adapt INTO the real graph model — there are no dict-fixtures.

Each spec describes one wagon: its theme, slug, and whether a module in its
source tree imports ``atdd.coach`` (the forbidden boundary crossing).
"""
from __future__ import annotations

import contextlib
import shutil
import tempfile

from pathlib import Path

from .._support.graph_loader import ConventionGraph, load_composed_graph

#: name -> wagon spec. VALID fragments must yield zero boundary violations.
VALID_FRAGMENTS: dict = {
    # A commons wagon whose source stays inside the commons boundary.
    "commons_wagon_no_coach_import": {
        "wagon": "do-thing", "theme": "commons", "imports_coach": False,
    },
    # A coach-themed wagon may freely import atdd.coach (its own layer).
    "coach_wagon_imports_coach": {
        "wagon": "drive-it", "theme": "coach", "imports_coach": True,
    },
}

#: name -> wagon spec. INVALID fragments must yield a boundary violation.
INVALID_FRAGMENTS: dict = {
    # A commons wagon whose source imports atdd.coach crosses the boundary.
    "commons_wagon_imports_coach": {
        "wagon": "do-thing", "theme": "commons", "imports_coach": True,
    },
}


def materialize_wagon(root: Path, *, wagon: str, theme: str, imports_coach: bool) -> None:
    """Write a single wagon (manifest + source module) under *root*."""
    pkg = wagon.replace("-", "_")
    wdir = root / "plan" / pkg
    wdir.mkdir(parents=True, exist_ok=True)
    (wdir / f"_{pkg}.yaml").write_text(
        f'wagon: {wagon}\nurn: "wagon:{wagon}"\ntheme: {theme}\n', encoding="utf-8"
    )
    src = root / "src" / "atdd" / pkg
    src.mkdir(parents=True, exist_ok=True)
    body = "import atdd.coach\n" if imports_coach else "VALUE = 1\n"
    (src / "runner.py").write_text(body, encoding="utf-8")


def build_graph(root: Path, *specs: dict) -> ConventionGraph:
    """Materialize *specs* under *root* and return the loaded composed graph."""
    for spec in specs:
        materialize_wagon(root, **spec)
    return load_composed_graph(root)


@contextlib.contextmanager
def fixtures_tmp():
    d = tempfile.mkdtemp(prefix="boundary-fix-")
    try:
        yield Path(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
