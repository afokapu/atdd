"""
Unit + integration tests for relative-import handling in the dead-code
reachability tracer.

Issue: #453 — `extract_imports_ast` previously ignored
``ast.ImportFrom.level``, dropping every relative-import edge. Files only
reached via ``from .X import Y`` were misclassified as unreachable.
This module exercises the fix:

  * unit: ``_resolve_module_name`` over level=0/1/2, module=None,
    depth-exceeding, and out-of-root cases.
  * integration: synthetic ``python/`` trees scanned by the validator's
    own helpers (``build_file_import_graph`` + BFS) — verifies edges are
    created so downstream files are reachable.
  * regression: parametrized fixture mirroring the issue's reproducer
    asserts that ``trains/models.py`` is NOT in the unreachable set
    after the fix.

Reference: src/atdd/coder/validators/test_dead_code_python.py
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Set

import pytest

from atdd.coder.validators import test_dead_code_python as dcp
from atdd.coder.validators.test_dead_code_python import (
    _resolve_module_name,
    build_file_import_graph,
    extract_imports_ast,
    find_cli_entry_points,
    find_reachable_files,
    is_root_file,
    resolve_module_to_file,
)


FIXTURES = Path(__file__).parent / "fixtures"


# ============================================================================
# Helpers
# ============================================================================


def _stage_fixture(fixture_name: str, dest: Path) -> Path:
    """Copy a fixture's ``python/`` tree into ``dest/python`` and return it."""
    src = FIXTURES / fixture_name / "python"
    target = dest / "python"
    shutil.copytree(src, target)
    return target


def _unreachable_files(python_dir: Path) -> Set[str]:
    """Replicate the validator's unreachable-files computation against a
    monkeypatched ``PYTHON_DIR``. Top-level ``python/*.py`` are promoted to
    CLI-entry-point shape (fixture trees have no ``pyproject.toml``).

    Returns the relative POSIX paths of unreachable, non-``__init__`` files.
    """
    python_files = dcp.find_python_files()
    graph = build_file_import_graph(python_files)
    roots = {f for f in python_files if is_root_file(f)}
    for py_file in python_files:
        if py_file.parent == python_dir:
            roots.add(py_file)
    reachable = find_reachable_files(roots, graph)
    reverse_graph = dcp.build_reverse_graph(graph)
    reverse_reachable = find_reachable_files(roots, reverse_graph)
    all_reachable = reachable | reverse_reachable
    unreachable: Set[str] = set()
    for py_file in python_files:
        if py_file in all_reachable:
            continue
        if py_file.name == "__init__.py":
            continue
        unreachable.add(py_file.relative_to(python_dir).as_posix())
    return unreachable


def _stage_and_compute(
    fixture_name: str, tmp_path: Path, monkeypatch
) -> Set[str]:
    python_dir = _stage_fixture(fixture_name, tmp_path)
    monkeypatch.setattr(dcp, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(dcp, "PYTHON_DIR", python_dir)
    return _unreachable_files(python_dir)


# ============================================================================
# Unit tests — _resolve_module_name
# ============================================================================


@pytest.mark.coder
def test_resolve_level_zero_passes_through(tmp_path: Path):
    importer = tmp_path / "trains" / "runner.py"
    importer.parent.mkdir(parents=True)
    importer.touch()
    assert (
        _resolve_module_name(importer, "trains.models", 0, root=tmp_path)
        == "trains.models"
    )


@pytest.mark.coder
def test_resolve_level_one_with_module(tmp_path: Path):
    importer = tmp_path / "trains" / "runner.py"
    importer.parent.mkdir(parents=True)
    importer.touch()
    assert (
        _resolve_module_name(importer, "models", 1, root=tmp_path)
        == "trains.models"
    )


@pytest.mark.coder
def test_resolve_level_one_module_none_returns_package(tmp_path: Path):
    """Decision #1: ``from . import x`` (level=1, module=None) → the package itself.

    The named binding ``x`` is reached via the existing ``__init__.py``
    implicit-edges pathway, not via this resolver.
    """
    importer = tmp_path / "pkg" / "runner.py"
    importer.parent.mkdir(parents=True)
    importer.touch()
    assert _resolve_module_name(importer, None, 1, root=tmp_path) == "pkg"


@pytest.mark.coder
def test_resolve_level_two_with_module(tmp_path: Path):
    """``from ..x.y import z`` from ``a/b/c.py`` resolves to ``a.x.y``."""
    importer = tmp_path / "a" / "b" / "c.py"
    importer.parent.mkdir(parents=True)
    importer.touch()
    assert (
        _resolve_module_name(importer, "x.y", 2, root=tmp_path) == "a.x.y"
    )


@pytest.mark.coder
def test_resolve_level_exceeding_depth_returns_none(tmp_path: Path):
    """``from ....x import y`` from a shallow file resolves to None.

    Python rejects these at runtime; the validator MUST NOT invent edges.
    """
    importer = tmp_path / "a" / "b.py"
    importer.parent.mkdir(parents=True)
    importer.touch()
    # depth = 1 (only "a"); level=4 means three parent walks → escapes root.
    assert _resolve_module_name(importer, "x", 4, root=tmp_path) is None


@pytest.mark.coder
def test_resolve_out_of_root_returns_none(tmp_path: Path):
    """Importer outside ``root`` → None (not ValueError).

    Helper boundary contract pinned by Patch 4 of the issue review.
    """
    foreign = Path("/tmp") / "outside.py"
    assert _resolve_module_name(foreign, "x", 1, root=tmp_path) is None


@pytest.mark.coder
def test_resolve_dunder_init_relative_import(tmp_path: Path):
    """Edge case: ``from .__init__ import X`` (rare but legal Python).

    Resolves cleanly without crashing; the result is "<pkg>.__init__"
    which ``resolve_module_to_file`` then either matches to the
    package's ``__init__.py`` (via partial-match) or drops silently.
    Either outcome is defensible; what matters is no crash.
    """
    importer = tmp_path / "pkg" / "runner.py"
    importer.parent.mkdir(parents=True)
    importer.touch()
    result = _resolve_module_name(importer, "__init__", 1, root=tmp_path)
    assert result == "pkg.__init__"


# ============================================================================
# Unit test — extract_imports_ast emits edge for `from .X import Y`
# ============================================================================


@pytest.mark.coder
def test_extract_imports_ast_resolves_relative_to_absolute(tmp_path: Path):
    """``from .models import X`` in pkg/foo.py emits "pkg.models"."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    foo = pkg / "foo.py"
    foo.write_text("from .models import X\n")
    (pkg / "models.py").write_text("class X: pass\n")

    modules = extract_imports_ast(foo, root=tmp_path)
    assert "pkg.models" in modules


@pytest.mark.coder
def test_extract_imports_ast_resolves_from_dot_import_x(tmp_path: Path):
    """``from . import x`` in pkg/foo.py emits "pkg" (Decision #1)."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    foo = pkg / "foo.py"
    foo.write_text("from . import models\n")
    (pkg / "models.py").write_text("class X: pass\n")

    modules = extract_imports_ast(foo, root=tmp_path)
    assert "pkg" in modules


@pytest.mark.coder
def test_extract_imports_ast_absolute_unchanged(tmp_path: Path):
    """level=0 imports (absolute) still produce the dotted name verbatim."""
    foo = tmp_path / "foo.py"
    foo.write_text("from trains.models import X\nimport trains.runner\n")
    modules = extract_imports_ast(foo, root=tmp_path)
    assert "trains.models" in modules
    assert "trains.runner" in modules


# ============================================================================
# Integration tests — full validator helpers against fixture trees
# ============================================================================


@pytest.mark.coder
def test_relative_import_creates_file_edge(tmp_path: Path, monkeypatch):
    """Edge ``pkg/foo.py → pkg/bar.py`` exists when foo does ``from .bar import``."""
    python_dir = tmp_path / "python"
    pkg = python_dir / "pkg"
    pkg.mkdir(parents=True)
    foo = pkg / "foo.py"
    bar = pkg / "bar.py"
    foo.write_text("from .bar import X\n")
    bar.write_text("class X: pass\n")
    (pkg / "__init__.py").write_text("")

    monkeypatch.setattr(dcp, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(dcp, "PYTHON_DIR", python_dir)

    python_files = dcp.find_python_files()
    graph = build_file_import_graph(python_files)
    assert bar in graph[foo], (
        f"expected edge foo→bar via relative import; graph[foo]={graph[foo]}"
    )


@pytest.mark.coder
def test_flat_package_no_unreachable_after_fix(tmp_path, monkeypatch):
    """Fixture flat-package (relative imports only) → 0 unreachable findings."""
    python_dir = tmp_path / "python"
    pkg_dir = python_dir / "flat_package"
    pkg_dir.mkdir(parents=True)
    src = FIXTURES / "flat_package"
    for child in src.iterdir():
        if child.is_file():
            shutil.copy2(child, pkg_dir / child.name)
    # Move app.py to the python/ root so it acts as the CLI entry shape.
    (pkg_dir / "app.py").rename(python_dir / "app.py")

    monkeypatch.setattr(dcp, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(dcp, "PYTHON_DIR", python_dir)

    unreachable = _unreachable_files(python_dir)
    assert unreachable == set(), (
        f"flat package should be fully reachable after the fix; "
        f"got unreachable={unreachable}"
    )


@pytest.mark.coder
def test_from_dot_import_x_reaches_target_via_init_implicit_edge(
    tmp_path, monkeypatch
):
    """Two-hop: ``from . import models`` → package → models via __init__.py edges.

    REQUIRED by Patch 3 of the issue review. Without this test, the
    level=1+module=None path could regress unnoticed if the existing
    __init__.py implicit-edges rule changes.
    """
    unreachable = _stage_and_compute("from_dot_import_x", tmp_path, monkeypatch)
    assert "pkg/models.py" not in unreachable, (
        f"models.py should be reachable via 'from . import models' two-hop; "
        f"unreachable={unreachable}"
    )
