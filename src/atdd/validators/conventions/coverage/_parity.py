"""Fault-injection + legacy-parity helpers for the `coverage` family tests (#1212).

Mirrors the differential method of ``_support.catch_matrix`` (inject one realistic
fault into the real tree, run BOTH the convention evaluator and the legacy pytest
target on the identical faulted tree, then revert) but scoped to this family so
the variant tests stay self-contained. Underscore-prefixed: not collected by pytest.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional

from .._support.graph_loader import load_composed_graph


def repo_root() -> Path:
    """The worktree root (…/src/atdd/validators/conventions/coverage -> root)."""
    return Path(__file__).resolve().parents[5]


@contextlib.contextmanager
def inject_tempfile(root: Path, relpath: str, content: str):
    p = root / relpath
    existed = p.exists()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')
    try:
        yield
    finally:
        if not existed:
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


def legacy_red(root: Path, target: str) -> bool:
    """True iff the legacy pytest target FAILS on the current tree."""
    rc = subprocess.run(
        [sys.executable, '-m', 'pytest', target, '-q', '-p', 'no:cacheprovider'],
        cwd=root, env={'PYTHONPATH': 'src', 'PATH': os.environ['PATH']},
        capture_output=True, text=True,
    ).returncode
    return rc != 0


def conv_violations(root: Path, evaluator: Callable, config: Optional[dict] = None) -> List[dict]:
    return evaluator(load_composed_graph(root), config)
