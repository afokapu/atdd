"""Fault-injection + legacy-parity helpers for the `coverage` family tests (#1212).

Mirrors the differential method of ``_support.catch_matrix`` (inject one realistic
fault into the real tree, run BOTH the convention evaluator and the legacy pytest
target on the identical faulted tree, then revert) but scoped to this family so
the variant tests stay self-contained. Underscore-prefixed: not collected by pytest.
"""
from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Callable, List, Optional

from .._support.graph_loader import load_composed_graph


def repo_root() -> Path:
    """The worktree root (…/src/atdd/validators/conventions/coverage -> root)."""
    return Path(__file__).resolve().parents[5]


@contextlib.contextmanager
def inject_tempfile(root: Path, relpath: str, content: str):
    # `relpath` is a synthetic fault probe (e.g. `_tmp_coverage_orphan_probe.convention.yaml`)
    # that must NEVER legitimately exist in the tree. The previous `if not existed: unlink`
    # guard meant a stale copy left by an interrupted run was treated as pre-existing and
    # never cleaned — sticky residue that a disk-rescanning baseline (`no_orphan`) then
    # flagged. Always remove the probe on exit so residue can never accumulate.
    p = root / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')
    try:
        yield
    finally:
        p.unlink(missing_ok=True)


@contextlib.contextmanager
def inject_patch(root: Path, relpath: str, old: str, new: str):
    p = root / relpath
    orig = p.read_text(encoding='utf-8')
    assert old in orig, f"patch anchor {old!r} not found in {relpath}"
    p.write_text(orig.replace(old, new, 1), encoding='utf-8')
    try:
        yield
    finally:
        p.write_text(orig, encoding='utf-8')


def conv_violations(root: Path, evaluator: Callable, config: Optional[dict] = None,
                    graph=None) -> List[dict]:
    """``graph`` lets a read-only caller pass the session-scoped clean graph (#1414);
    callers that have mutated the tree must omit it so the graph is re-read."""
    g = graph if graph is not None else load_composed_graph(root)
    return evaluator(g, config)
