# URN: test:govern-lifecycle:config-driven-four-tier-validators:E048-UNIT-001-toolkit-files-discovered-under-src-atdd
# Acceptance: acc:govern-lifecycle:E048-UNIT-001-toolkit-files-discovered-under-src-atdd
# Acceptance: acc:govern-lifecycle:E048-UNIT-002-cross-wagon-attribution-strips-atdd-prefix
# WMBT: wmbt:govern-lifecycle:E048
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E048 — config-drive the wagon-boundaries validator onto the toolkit.

``test_wagon_boundaries.py`` pins ``PYTHON_DIR = REPO_ROOT / "python"`` and roots
every finder there, so the toolkit's own wagons under ``src/atdd`` are never
scanned. The discovery root (``src/atdd``, wagons one level under it) must be
reconciled with the import-resolution root: toolkit code imports cross-wagon as
``atdd.<wagon>...`` — the wagon is the SECOND import segment because the import
root is ``src`` and ``atdd`` is the top package. Wagon attribution must strip the
``atdd.`` import-prefix or every toolkit import is mis-attributed.

RED state: the toolkit-aware finder/attribution surface
(``find_implementation_files(roots=...)``, ``get_wagon_from_path(path, scan_root)``,
``is_cross_wagon_import(path, import_path, scan_root)``) does not exist yet.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coder.validators._toolkit_roots import ScanRoot, resolve_scan_roots
from atdd.coder.validators.test_wagon_boundaries import (
    find_implementation_files,
    get_wagon_from_path,
    is_cross_wagon_import,
)

pytestmark = [pytest.mark.platform]

REPO_ROOT = find_repo_root()
TOOLKIT_CONFIG = {"code": {"toolkit": "src/atdd"}}


def _toolkit_scan_root() -> ScanRoot:
    roots = resolve_scan_roots(TOOLKIT_CONFIG, REPO_ROOT)
    toolkit = [r for r in roots if r.discovery_root == REPO_ROOT / "src/atdd"]
    assert toolkit, "code.toolkit must yield a toolkit ScanRoot"
    return toolkit[0]


def test_toolkit_implementation_files_discovered_and_fixtures_excluded():
    """E048-UNIT-001: finders enumerate src/atdd impl files but skip fixtures/."""
    scan_root = _toolkit_scan_root()
    impls = find_implementation_files(roots=[scan_root])
    posix = {p.as_posix() for p in impls}

    known = (
        REPO_ROOT
        / "src/atdd/consolidate_coach_workspace/enforce_surface_conformance"
        / "src/application/apply_layout_use_case.py"
    )
    assert known.as_posix() in posix, "a known toolkit impl file must be discovered"
    assert not any("coder/validators/fixtures" in p for p in posix), (
        "negative fixtures under coder/validators/fixtures/ must be excluded"
    )


def _make_toolkit_tree(base: Path) -> ScanRoot:
    """Synthesize src/<pkg>/<wagonA|wagonB>/<feature>/src/<layer> under *base*."""
    src = base / "src"
    pkg = src / "atdd"
    for wagon in ("wagon_a", "wagon_b"):
        (pkg / wagon / "feat" / "src" / "domain").mkdir(parents=True, exist_ok=True)
        (pkg / wagon / "__init__.py").write_text("", encoding="utf-8")
    return ScanRoot(discovery_root=pkg, import_root=src, import_prefix="atdd")


def test_cross_wagon_attribution_strips_atdd_prefix(tmp_path):
    """E048-UNIT-002: atdd.<wagonB> is cross-wagon; atdd.<wagonA> (self) is not."""
    scan_root = _make_toolkit_tree(tmp_path)
    src_file = scan_root.discovery_root / "wagon_a" / "feat" / "src" / "domain" / "thing.py"
    src_file.write_text("x = 1\n", encoding="utf-8")

    # The wagon of the source file is recovered from the discovery root.
    assert get_wagon_from_path(src_file, scan_root) == "wagon_a"

    # An import into a different toolkit wagon, carrying the atdd. prefix.
    is_cross, source, target = is_cross_wagon_import(
        src_file,
        "atdd.wagon_b.feat.src.domain.other",
        scan_root,
    )
    assert is_cross is True
    assert source == "wagon_a"
    assert target == "wagon_b"

    # A same-wagon import must NOT be flagged as cross-wagon.
    self_cross, _, _ = is_cross_wagon_import(
        src_file,
        "atdd.wagon_a.feat.src.application.use_case",
        scan_root,
    )
    assert self_cross is False
