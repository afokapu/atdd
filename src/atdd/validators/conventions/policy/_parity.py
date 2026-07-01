"""Legacy-parity harness for the `policy` family variants (#1212).

Each policy variant must reach *both*-catch parity: when a variant's fault is
injected into the relevant REAL repo file, the convention evaluator (over the real
composed graph) AND the legacy validator (run via subprocess `python -m pytest
<nodeid>`) must both catch it. This module supplies the shared injection +
subprocess plumbing; it is not a test module (no ``test_`` prefix → not collected).
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def repo_root() -> Path:
    # .../src/atdd/validators/conventions/policy/_parity.py
    return Path(__file__).resolve().parents[5]


def legacy_catches(nodeid: str) -> bool:
    """Run the legacy validator test by nodeid; return True iff it FAILS (i.e. the
    legacy validator caught the injected fault)."""
    root = repo_root()
    env = dict(os.environ)
    env["PYTHONPATH"] = "src"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", nodeid, "-q", "-p", "no:cacheprovider"],
        cwd=str(root), env=env, capture_output=True, text=True,
    )
    return proc.returncode != 0


@contextlib.contextmanager
def overwrite_file(path: Path, new_content: str):
    """Back up *path*, replace its content, restore the exact original bytes on exit."""
    original = path.read_bytes()
    try:
        path.write_text(new_content, encoding="utf-8")
        yield
    finally:
        path.write_bytes(original)


@contextlib.contextmanager
def temp_new_file(path: Path, content: str):
    """Create *path* with *content*, delete it on exit (must not pre-exist)."""
    assert not path.exists(), f"parity temp file already exists: {path}"
    try:
        path.write_text(content, encoding="utf-8")
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
