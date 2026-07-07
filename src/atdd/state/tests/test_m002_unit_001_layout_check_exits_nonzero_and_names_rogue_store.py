# URN: test:drive-state-machine:consolidate-store-writes:M002-UNIT-001-layout-check-exits-nonzero-and-names-rogue-store
# Acceptance: acc:drive-state-machine:M002-UNIT-001-layout-check-exits-nonzero-and-names-rogue-store
# WMBT: wmbt:drive-state-machine:M002
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: layout --check returns a non-zero exit and names the offending per-worktree store when a child worktree carries its own state.sqlite in sibling-worktree mode.
"""RED Test for test:drive-state-machine:consolidate-store-writes:M002-UNIT-001.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: RED
WMBT: wmbt:drive-state-machine:M002
Purpose: the single-store guard bites at the CLI — a rogue per-worktree store
below the Control Root makes `atdd state layout --check` fail and name it.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state import cli as state_cli


def _mk_marked(path: Path) -> Path:
    (path / ".git").mkdir(parents=True, exist_ok=True)
    (path / ".atdd").mkdir(parents=True, exist_ok=True)
    (path / ".atdd" / "config.yaml").write_text("x\n", encoding="utf-8")
    (path / ".atdd" / "manifest.yaml").write_text("version: '2.0'\n", encoding="utf-8")
    return path


def test_layout_check_exits_nonzero_and_names_rogue_store(tmp_path, capsys, monkeypatch):
    project = tmp_path / "project"
    _mk_marked(project / "main")
    wt = _mk_marked(project / "wt1")
    (project / ".atdd" / "state").mkdir(parents=True)
    (project / ".atdd" / "state" / "state.sqlite").touch()
    rogue = wt / ".atdd" / "state" / "state.sqlite"
    rogue.parent.mkdir(parents=True)
    rogue.touch()

    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(project))
    rc = state_cli.run(["layout", "--check", "--root", str(project)])
    out = capsys.readouterr().out

    assert rc != 0
    assert str(rogue) in out
