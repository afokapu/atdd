"""Shared fixtures + on-disk fault-injection helpers for presence variant tests (#1212).

The presence variant tests prove real-graph execution AND legacy parity:
  - clean baseline against the REAL composed graph (0 violations),
  - inject a fault into the relevant real file -> convention evaluator catches it
    AND the legacy validator (run via subprocess) catches it -> revert.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _find_repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


@pytest.fixture
def repo_root() -> Path:
    return _find_repo_root()


@contextlib.contextmanager
def patched(repo_root: Path, rel: str, old: str, new: str):
    """Replace the first occurrence of ``old`` with ``new`` in ``repo_root/rel``,
    restoring the original content on exit."""
    p = repo_root / rel
    orig = p.read_text(encoding="utf-8")
    assert old in orig, f"anchor {old!r} not found in {rel}"
    p.write_text(orig.replace(old, new, 1), encoding="utf-8")
    try:
        yield
    finally:
        p.write_text(orig, encoding="utf-8")


@contextlib.contextmanager
def temp_file(repo_root: Path, rel: str, content: str):
    """Create ``repo_root/rel`` with ``content``; remove it on exit."""
    p = repo_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    try:
        yield
    finally:
        p.unlink(missing_ok=True)


def legacy_catches(repo_root: Path, nodeid: str) -> bool:
    """Run a legacy pytest nodeid in a subprocess; True iff it FAILS (non-zero)."""
    rc = subprocess.run(
        [sys.executable, "-m", "pytest", nodeid, "-q", "-p", "no:cacheprovider"],
        cwd=repo_root,
        env={"PYTHONPATH": "src", "PATH": os.environ["PATH"]},
        capture_output=True, text=True,
    ).returncode
    return rc != 0
