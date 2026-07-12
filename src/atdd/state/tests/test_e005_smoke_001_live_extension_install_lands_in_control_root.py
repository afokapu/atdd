# URN: test:drive-state-machine:consolidate-store-writes:E005-SMOKE-001-live-extension-install-lands-in-control-root
# Acceptance: acc:drive-state-machine:E005-SMOKE-001-live-extension-install-lands-in-control-root
# WMBT: wmbt:drive-state-machine:E005
# Phase: SMOKE
# Runtime: python
# Layer: integration
# Assertion: behavioral
# Purpose: A real substrate install issued from a worktree lands under the single control-root .atdd/extensions/, not the worktree.
"""SMOKE Test for test:drive-state-machine:consolidate-store-writes:E005-SMOKE-001.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: SMOKE
WMBT: wmbt:drive-state-machine:E005
Purpose: over a real git worktree, the substrate operational-root resolver + the
installer's package_home place an extension install under the control-root
.atdd/extensions/, never the worktree.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from atdd.state.paths import resolve_operational_root
from atdd.substrate import installer

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git required for the live worktree smoke")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def test_live_extension_install_lands_in_control_root(tmp_path):
    project = tmp_path / "project"
    main = project / "main"
    main.mkdir(parents=True)
    _git(main, "init", "-q")
    _git(main, "config", "user.email", "t@t.t")
    _git(main, "config", "user.name", "t")
    (main / ".atdd").mkdir()
    (main / ".atdd" / "config.yaml").write_text("x\n")
    (main / "f.txt").write_text("x\n")
    _git(main, "add", "-A")
    _git(main, "commit", "-qm", "init")
    wt1 = project / "wt1"
    _git(main, "worktree", "add", "-q", str(wt1), "-b", "wt1")

    # the substrate install path resolves from the worktree to the control root
    root = resolve_operational_root(wt1)
    home = installer.install_path(root, "extension", "atdd.extension.demo", "0.1.0")
    home.mkdir(parents=True)
    (home / "marker").write_text("ok\n")

    assert home == project / ".atdd" / "extensions" / "atdd.extension.demo" / "0.1.0"
    assert not (wt1 / ".atdd" / "extensions").exists()
