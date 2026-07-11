# URN: test:project-shared-state:mint-object-identity:Y001-UNIT-001-rename-does-not-move-file
# Acceptance: acc:project-shared-state:Y001-UNIT-001-rename-does-not-move-file
# WMBT: wmbt:project-shared-state:Y001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: Renaming a slug creates no second projection file and deletes none — still exactly one file, still named <uid>.yaml. Refs #1433.
"""A slug rename does not move the projection file (Y001-UNIT-001).

wagon: project-shared-state | feature: mint-object-identity | phase: RED
WMBT: wmbt:project-shared-state:Y001

Slug and title are mutable display metadata. If a rename moved the file, git would
see a delete plus a create, the object's history would fork, and a peer merging the
rename would resurrect the old path. Refs #1433 / #1400.
"""
from __future__ import annotations

from atdd.state.projection import project
from atdd.state.work_item_writer import mint_work_item, rename_work_item

from ._helpers import memory_store


def test_y001_unit_001_rename_does_not_move_file(tmp_path) -> None:
    """After renaming feature-x → feature-y, still exactly one file: <uid>.yaml."""
    out_dir = tmp_path / "projection"
    with memory_store() as (conn, store):
        obj = mint_work_item(conn, slug="feature-x", owner_actor="dev-a")
        project(store, out_dir)
        before = sorted(p.name for p in out_dir.iterdir())
        assert before == [f"{obj.uid}.yaml"]

        renamed = rename_work_item(conn, obj.uid, slug="feature-y")
        assert renamed.uid == obj.uid
        project(store, out_dir)

    after = sorted(p.name for p in out_dir.iterdir())

    # Still exactly one projection file and it is still named <uid>.yaml.
    assert after == [f"{obj.uid}.yaml"]

    # No file named for either slug was created, and no file was deleted.
    assert not list(out_dir.glob("*feature-x*"))
    assert not list(out_dir.glob("*feature-y*"))
    assert after == before
