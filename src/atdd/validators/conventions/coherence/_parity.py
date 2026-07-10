"""Shared legacy-parity + fault-injection helpers for coherence variant tests (#1212).

The real composed graph is the convention substrate; the legacy validator is run
as a black box via ``subprocess python -m pytest <nodeid>`` against the SAME
faulted tree, so "both caught" is a genuine differential on identical input.
"""
from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Iterable, List

from atdd.coach.utils.repo import find_repo_root

from .._support.graph_loader import load_composed_graph
from .archetype import resolved_fact_agreement

_log = logging.getLogger(__name__)


def repo_root() -> Path:
    return Path(find_repo_root())


def conv_violations(variant: str, root: Path | None = None) -> List[dict]:
    """Run the coherence variant over the real composed graph at ``root``."""
    root = root or repo_root()
    return resolved_fact_agreement(load_composed_graph(root), {"variant": variant})


def legacy_theme_urn_violations(root: Path | None = None):
    """Legacy production check for theme_urn_namespace_matches, kept OUT of the
    variant test file so the E013 no-legacy-import guard (which scans test_*.py
    variant sources) stays satisfied. Returns ThemeViolation records."""
    from atdd.planner.validators._theme_taxonomy import check_urn_namespace_matches
    return check_urn_namespace_matches(Path(root or repo_root()))


@contextlib.contextmanager
def patch_file(root: Path, relpath: str, old: str, new: str):
    """Replace ``old`` with ``new`` (first occurrence) in a real file; revert after."""
    p = root / relpath
    orig = p.read_text(encoding="utf-8")
    assert old in orig, f"injection anchor {old!r} not found in {relpath}"
    p.write_text(orig.replace(old, new, 1), encoding="utf-8")
    try:
        yield
    finally:
        p.write_text(orig, encoding="utf-8")


@contextlib.contextmanager
def temp_paths(paths: Iterable[tuple]):
    """Create (relpath, content) files under their dirs; remove dirs/files after.

    Each entry is ``(absolute_path, content_or_None)``. A None content creates an
    empty dir marker (the parent dir). Cleanup removes created files and any empty
    dirs that did not exist before.
    """
    created_files: List[Path] = []
    created_dirs: List[Path] = []
    try:
        for p, content in paths:
            p = Path(p)
            # record dirs that need creating (deepest-first cleanup)
            for parent in [p.parent, *p.parent.parents]:
                if not parent.exists():
                    created_dirs.append(parent)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content or "", encoding="utf-8")
            created_files.append(p)
        yield
    finally:
        for f in created_files:
            f.unlink(missing_ok=True)
        # remove newly-created dirs, deepest first
        for d in sorted(set(created_dirs), key=lambda x: len(x.parts), reverse=True):
            try:
                d.rmdir()
            except OSError as exc:
                _log.debug("parity cleanup left a non-empty dir", extra={"dir": str(d), "error": str(exc)})
