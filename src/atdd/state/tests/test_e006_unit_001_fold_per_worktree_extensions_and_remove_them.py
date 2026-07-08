# URN: test:drive-state-machine:consolidate-store-writes:E006-UNIT-001-fold-per-worktree-extensions-and-remove-them
# Acceptance: acc:drive-state-machine:E006-UNIT-001-fold-per-worktree-extensions-and-remove-them
# WMBT: wmbt:drive-state-machine:E006
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: Consolidation copies a per-worktree extension the control root lacks into the control-root .atdd/extensions/ and removes the per-worktree copy.
"""RED Test for test:drive-state-machine:consolidate-store-writes:E006-UNIT-001.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: RED
WMBT: wmbt:drive-state-machine:E006
Purpose: migrate_layout folds per-worktree extension/workspace installs into the
control-root .atdd/, unions the substrate lock, and removes the per-worktree
copies.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from atdd.state.cli import migrate_layout
from atdd.state.db import connect, init_state_store


def _mk_ext(atdd: Path, kind_dir: str, pid: str, ver: str) -> None:
    home = atdd / kind_dir / pid / ver
    home.mkdir(parents=True)
    (home / "marker").write_text("from-worktree\n")


def test_fold_per_worktree_extensions_and_remove_them(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    # control-root .atdd/ with a store but no extensions
    connect(init_state_store(db_path=project / ".atdd" / "state" / "state.sqlite")).close()

    wt = project / "wt1"
    (wt / ".git").mkdir(parents=True)
    wt_atdd = wt / ".atdd"
    _mk_ext(wt_atdd, "extensions", "atdd.extension.demo", "0.1.0")
    _mk_ext(wt_atdd, "workspaces", "atdd.workspace.demo", "0.1.0")
    (wt_atdd / "substrate.lock.yaml").write_text(yaml.safe_dump({
        "schema_version": "1.0.0",
        "artifacts": [
            {"id": "atdd.extension.demo", "kind": "extension", "version": "0.1.0",
             "installed_path": ".atdd/extensions/atdd.extension.demo/0.1.0", "enabled": True},
            {"id": "atdd.workspace.demo", "kind": "workspace", "version": "0.1.0",
             "installed_path": ".atdd/workspaces/atdd.workspace.demo/0.1.0", "enabled": True},
        ],
    }))

    result = migrate_layout(project_root=project)

    croot = project / ".atdd"
    # folded into the control root
    assert (croot / "extensions" / "atdd.extension.demo" / "0.1.0" / "marker").is_file()
    assert (croot / "workspaces" / "atdd.workspace.demo" / "0.1.0" / "marker").is_file()
    # lock unioned at the control root
    lock = yaml.safe_load((croot / "substrate.lock.yaml").read_text())
    ids = {a["id"] for a in lock["artifacts"]}
    assert {"atdd.extension.demo", "atdd.workspace.demo"} <= ids
    # per-worktree operational copies removed
    assert not (wt_atdd / "extensions").exists()
    assert not (wt_atdd / "workspaces").exists()
    # result reports the operational fold
    assert result.extensions_folded >= 2
    assert any("wt1" in str(p) for p in result.operational_removed)
