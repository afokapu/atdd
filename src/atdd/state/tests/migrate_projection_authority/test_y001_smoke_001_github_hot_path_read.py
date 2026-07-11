# URN: test:migrate-projection-authority:remove-github-reads:Y001-SMOKE-001-github-hot-path-read
# Acceptance: acc:migrate-projection-authority:Y001-SMOKE-001-github-hot-path-read
# WMBT: wmbt:migrate-projection-authority:Y001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state hot-path` command exits 0 against this checkout with a `gh` shim first on PATH that would EXPLODE if any lifecycle decision shelled out to it; and the full lifecycle (create → transition → project → canonicality) completes with the shim armed, no GitHub reachable, and zero providers registered. Refs #1434.
"""SMOKE — the lifecycle runs with GitHub booby-trapped (Y001-SMOKE-001).

wagon: migrate-projection-authority | feature: remove-github-reads | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:Y001

The static guard proves the source does not reach GitHub. This proves the *running system* does not
— which is a different claim, and the one that matters at 3am.

The instrument is a ``gh`` shim placed first on ``PATH`` that exits non-zero and writes its
invocation to a file. Then the whole lifecycle is driven through the real CLI against a real store
and a real projection, with no GitHub remote and no provider registered. If any lifecycle decision
shells out to ``gh``, the file exists and this test fails — and it fails with the argv, so you know
which one. Refs #1434 / #1400.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ._live import make_checkout

_SRC = Path(__file__).resolve().parents[4]


def _arm_gh_trap(bin_dir: Path, witness: Path) -> Path:
    """A `gh` first on PATH that records any invocation and fails."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "gh"
    shim.write_text(
        "#!/bin/sh\n"
        f'echo "gh $*" >> "{witness}"\n'
        'echo "a lifecycle decision shelled out to gh" >&2\n'
        "exit 97\n"
    )
    shim.chmod(0o755)
    return shim


def _atdd(root: Path, bin_dir: Path, *args: str) -> subprocess.CompletedProcess:
    """`atdd state ...` with the gh trap armed and GitHub unreachable."""
    env = {
        "PYTHONPATH": str(_SRC),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "HOME": str(root),
        "CI": "true",
        # Any real network call to GitHub would have to get past these, too.
        "GH_TOKEN": "", "GITHUB_TOKEN": "",
    }
    return subprocess.run(
        [sys.executable, "-m", "atdd", "state", *args, "--root", str(root)],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=180,
    )


def test_y001_smoke_001_github_hot_path_read(tmp_path) -> None:
    """The full lifecycle completes with `gh` booby-trapped and zero providers registered."""
    repo = make_checkout(tmp_path / "repo")
    bin_dir = tmp_path / "bin"
    witness = tmp_path / "gh-was-called.txt"
    _arm_gh_trap(bin_dir, witness)

    # The static guard, through the shipped command.
    guard = _atdd(repo, bin_dir, "hot-path")
    assert guard.returncode == 0, guard.stdout + guard.stderr
    assert "GitHub-free" in guard.stdout

    # Zero providers. Core's default, and the state it ships in.
    listed = _atdd(repo, bin_dir, "providers")
    assert listed.returncode == 0
    assert "no SyncProvider is registered" in listed.stdout

    # Now drive the whole lifecycle with the trap armed.
    assert _atdd(repo, bin_dir, "init").returncode == 0

    created = _atdd(repo, bin_dir, "object", "create", "--slug", "widget", "--owner", "dev-a")
    assert created.returncode == 0, created.stderr
    uid = created.stdout.strip()

    for step in (
        ("project",),
        ("canonicality",),
        ("object", "rename", uid, "--slug", "widget-v2"),
        ("project",),
        ("canonicality",),
        ("shadow",),
        ("digest",),
    ):
        result = _atdd(repo, bin_dir, *step)
        assert result.returncode == 0, f"{step} failed: {result.stdout}{result.stderr}"

    # The trap never fired. No lifecycle decision reached for GitHub — not once, across create,
    # rename, project, canonicality, shadow and digest.
    assert not witness.exists(), (
        f"a lifecycle decision shelled out to gh: {witness.read_text()}"
    )
