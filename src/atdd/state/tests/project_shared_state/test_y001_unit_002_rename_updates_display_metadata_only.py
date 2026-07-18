# URN: test:project-shared-state:mint-object-identity:Y001-UNIT-002-rename-updates-display-metadata-only
# Acceptance: acc:project-shared-state:Y001-UNIT-002-rename-updates-display-metadata-only
# WMBT: wmbt:project-shared-state:Y001
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A slug rename updates only the display fields inside the existing document — uid unchanged, filename unchanged, but the projection digest moves, proving the rename was captured. Refs #1433.
"""A rename touches display metadata and nothing else (Y001-UNIT-002).

wagon: project-shared-state | feature: mint-object-identity | phase: GREEN
WMBT: wmbt:project-shared-state:Y001

The digest moving while the filename does not is the whole point: the rename IS
shared state (peers must see it), but it is not identity. Refs #1433 / #1400.
"""
from __future__ import annotations

import yaml

from atdd.state.projection import project, projection_digest
from atdd.state.work_item_writer import mint_work_item, rename_work_item

from ._helpers import memory_store


def test_y001_unit_002_rename_updates_display_metadata_only(tmp_path) -> None:
    """slug becomes feature-y, uid is unchanged, the digest moves, the filename does not."""
    out_dir = tmp_path / "projection"
    with memory_store() as (conn, store):
        obj = mint_work_item(conn, slug="feature-x", owner_actor="dev-a", title="Feature X")
        project(store, out_dir)
        before_digest = projection_digest(out_dir)
        before_name = (out_dir / f"{obj.uid}.yaml").name

        rename_work_item(conn, obj.uid, slug="feature-y")
        project(store, out_dir)

    document = yaml.safe_load((out_dir / f"{obj.uid}.yaml").read_text(encoding="utf-8"))

    # The document's slug field becomes feature-y while its uid field is unchanged.
    assert document["slug"] == "feature-y"
    assert document["uid"] == obj.uid
    assert document["title"] == "Feature X"

    # The digest changes — the rename was captured — but the filename does not.
    after_digest = projection_digest(out_dir)
    assert after_digest != before_digest
    assert (out_dir / f"{obj.uid}.yaml").name == before_name
