# URN: test:project-shared-state:mint-object-identity:E004-UNIT-002-uid-names-projection-file
# Acceptance: acc:project-shared-state:E004-UNIT-002-uid-names-projection-file
# WMBT: wmbt:project-shared-state:E004
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: The projection filename is derived from the uid alone — no emitted path contains the object's slug or title. Refs #1433.
"""The uid alone names the projection file (E004-UNIT-002).

wagon: project-shared-state | feature: mint-object-identity | phase: GREEN
WMBT: wmbt:project-shared-state:E004

If the slug named the file, renaming it would move the object's whole git history
to a new path — a rename would read as a delete plus a create. Refs #1433 / #1400.
"""
from __future__ import annotations

from atdd.state.projection import project
from atdd.state.work_item_writer import mint_work_item

from ._helpers import memory_store

_SLUG = "feature-x"
_TITLE = "A Human Readable Title"


def test_e004_unit_002_uid_names_projection_file(tmp_path) -> None:
    """Exactly one file is written, named <uid>.yaml; no path carries slug or title."""
    with memory_store() as (conn, store):
        obj = mint_work_item(conn, slug=_SLUG, owner_actor="dev-a", title=_TITLE)
        assert obj.uid != _SLUG

        result = project(store, tmp_path / "projection")

    written = sorted((tmp_path / "projection").iterdir())

    # Exactly one file is written and its name is <uid>.yaml.
    assert [p.name for p in written] == [f"{obj.uid}.yaml"]
    assert result.files == {obj.uid: written[0]}

    # No emitted path contains the object's slug or title.
    for path in written:
        assert _SLUG not in str(path)
        assert _TITLE not in str(path)
