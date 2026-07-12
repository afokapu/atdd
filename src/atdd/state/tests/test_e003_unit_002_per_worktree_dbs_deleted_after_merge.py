# URN: test:drive-state-machine:consolidate-store-writes:E003-UNIT-002-per-worktree-dbs-deleted-after-merge
# Acceptance: acc:drive-state-machine:E003-UNIT-002-per-worktree-dbs-deleted-after-merge
# WMBT: wmbt:drive-state-machine:E003
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: After a successful merge the per-worktree state.sqlite files are removed so they cannot re-diverge; the control-root store remains.
"""RED Test for test:drive-state-machine:consolidate-store-writes:E003-UNIT-002.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: RED
WMBT: wmbt:drive-state-machine:E003
Purpose: consolidation deletes the per-worktree DBs (not merely reports them
abandoned) and leaves exactly one store at the control root.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state.cli import migrate_layout
from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore

WORK_ITEM = "work_item"


def _store_at(db_path: Path) -> StateStore:
    return StateStore(connect(init_state_store(db_path=db_path)))


def _mk_child_store(project: Path, name: str, uid: str) -> Path:
    child = project / name
    (child / ".git").mkdir(parents=True, exist_ok=True)
    (child / ".atdd" / "state").mkdir(parents=True, exist_ok=True)
    db = child / ".atdd" / "state" / "state.sqlite"
    st = _store_at(db)
    st.objects.upsert(uid, WORK_ITEM, state="RED")
    return db


def test_per_worktree_dbs_deleted_after_merge(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    # target control-root store
    _store_at(project / ".atdd" / "state" / "state.sqlite")

    wt1_db = _mk_child_store(project, "wt1", "wi-a")
    wt2_db = _mk_child_store(project, "wt2", "wi-b")
    assert wt1_db.is_file() and wt2_db.is_file()

    result = migrate_layout(project_root=project)

    shared = project / ".atdd" / "state" / "state.sqlite"
    assert shared.is_file()
    # both per-worktree DBs are gone (deleted, not abandoned)
    assert not wt1_db.exists()
    assert not wt2_db.exists()
    # and the result names what it deleted
    deleted = {Path(p).resolve() for p in result.deleted}
    assert wt1_db.resolve() in deleted
    assert wt2_db.resolve() in deleted
    # the merged rows survive in the single store
    check = StateStore(connect(shared))
    uids = {o.uid for o in check.objects.list(kind=WORK_ITEM)}
    assert {"wi-a", "wi-b"} <= uids
