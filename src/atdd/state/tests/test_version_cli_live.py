# URN: test:state-store:state-cli:live-version
# Issue: #1172 (State Store owns version source-of-truth)
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""#1172 SMOKE — live end-to-end of `atdd state version` (show / emit / bump).

Drives the real installed-form CLI (`python -m atdd state version ...`) via
subprocess against a real on-disk Control Root (run-or-fail, no skip): emit
reports the seeded version, bump advances it + persists, show reflects the bump.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3]


def _mk_root(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    (path / ".atdd").mkdir(parents=True, exist_ok=True)
    (path / ".atdd" / "config.yaml").write_text("x\n", encoding="utf-8")
    return path


def _version(root: Path, *args):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""),
           "HOME": str(root), "CI": "true"}
    return subprocess.run(
        [sys.executable, "-m", "atdd", "state", "version", *args, "--root", str(root)],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=60,
    )


def test_version_emit_then_bump_then_show_live(tmp_path):
    root = _mk_root(tmp_path / "repo")

    # emit — build-consumable seeded version (init happens lazily on first open).
    r = _version(root, "emit")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "3.149.0"

    # bump MINOR — writes the store.
    r = _version(root, "bump", "--class", "MINOR", "--pr", "1172")
    assert r.returncode == 0, r.stderr
    assert "3.150.0" in r.stdout

    # show — reflects the persisted bump.
    r = _version(root, "show")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "Release version: 3.150.0" in out
    assert "Bumps recorded:  1" in out

    # emit again — persisted across processes.
    r = _version(root, "emit")
    assert r.stdout.strip() == "3.150.0"
