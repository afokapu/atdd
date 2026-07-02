# URN: test:govern-lifecycle:pre-commit:branch-gate-store-backed
# Issue: #1323 (#1270 slice C — decommission the manifest mirror)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1270 slice C — the pre-commit branch-registration gate is store-backed.

The hook no longer greps `.atdd/manifest.yaml` for `slug:`; it delegates to
`atdd issue is-registered "$BRANCH"` (store-first, manifest fallback) and blocks
only when that helper exits non-zero. When atdd is unavailable the gate is
skipped (never hard-breaks a commit). Executed as a real subprocess with a
controllable fake `atdd` on PATH.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOK_PATH = REPO_ROOT / "src/atdd/coach/templates/hooks/pre-commit"

_GIT_CONFIG = [("user.email", "test@atdd.test"), ("user.name", "atdd test")]


def _init_repo(tmp_path: Path, branch: str) -> None:
    subprocess.run(["git", "init", "-q", "-b", branch, str(tmp_path)], check=True, capture_output=True)
    for k, v in _GIT_CONFIG:
        subprocess.run(["git", "-C", str(tmp_path), "config", k, v], check=True, capture_output=True)
    seed = tmp_path / "seed.txt"
    seed.write_text("seed\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "seed.txt"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "seed"], check=True, capture_output=True)


def _stage_code(tmp_path: Path) -> None:
    code = tmp_path / "src" / "module.py"
    code.parent.mkdir(parents=True, exist_ok=True)
    code.write_text("x = 1\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", str(code.relative_to(tmp_path))], check=True, capture_output=True)


def _fake_atdd_bin(tmp_path: Path, present: bool) -> Path:
    """A PATH dir with a real `git` symlink and (optionally) a fake `atdd`."""
    bind = tmp_path / "fakebin"
    bind.mkdir(exist_ok=True)
    (bind / "git").symlink_to(shutil.which("git"))
    if present:
        atdd = bind / "atdd"
        atdd.write_text("#!/bin/sh\nexit ${ATDD_FAKE_RC:-0}\n")
        atdd.chmod(0o755)
    return bind


def _run_hook(tmp_path: Path, *, atdd_present: bool, fake_rc: int = 0) -> subprocess.CompletedProcess:
    bind = _fake_atdd_bin(tmp_path, atdd_present)
    # fakebin first (its `atdd` wins when present); system dirs supply sh/git but
    # NOT atdd (pipx installs to ~/.local/bin, absent here) — so when the fake is
    # not created, `command -v atdd` fails and the gate must skip.
    env = {**os.environ, "PATH": f"{bind}:/usr/bin:/bin", "ATDD_FAKE_RC": str(fake_rc)}
    return subprocess.run([shutil.which("sh") or "sh", str(HOOK_PATH)],
                          cwd=str(tmp_path), env=env, capture_output=True, text=True)


# --- content -------------------------------------------------------------- #
def test_hook_delegates_to_is_registered_not_grep():
    text = HOOK_PATH.read_text()
    assert "atdd issue is-registered" in text, "hook must call the store-backed helper"
    assert 'grep -q "slug:' not in text, "hook must not grep the manifest for slug anymore"


# --- execution ------------------------------------------------------------ #
def test_blocks_when_helper_reports_unregistered(tmp_path):
    _init_repo(tmp_path, branch="feat/some-slug")
    _stage_code(tmp_path)
    r = _run_hook(tmp_path, atdd_present=True, fake_rc=1)  # helper: not registered
    assert r.returncode == 1, f"expected block; rc={r.returncode}\n{r.stderr}"
    assert "not registered" in r.stderr.lower()


def test_allows_when_helper_reports_registered(tmp_path):
    _init_repo(tmp_path, branch="feat/some-slug")
    _stage_code(tmp_path)
    r = _run_hook(tmp_path, atdd_present=True, fake_rc=0)  # helper: registered
    assert r.returncode == 0, f"expected allow; rc={r.returncode}\n{r.stderr}"


def test_skips_when_atdd_unavailable(tmp_path):
    _init_repo(tmp_path, branch="feat/some-slug")
    _stage_code(tmp_path)
    r = _run_hook(tmp_path, atdd_present=False)
    assert r.returncode == 0, f"gate must skip when atdd is absent; rc={r.returncode}\n{r.stderr}"
