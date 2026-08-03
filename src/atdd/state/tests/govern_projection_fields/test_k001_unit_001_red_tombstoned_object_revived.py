# URN: test:govern-projection-fields:mark-object-tombstone:K001-UNIT-001-red-tombstoned-object-revived
# Acceptance: acc:govern-projection-fields:K001-UNIT-001-red-tombstoned-object-revived
# WMBT: wmbt:govern-projection-fields:K001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: a merge whose incoming side sets a live phase on a TOMBSTONED object is refused with a resurrection conflict naming the uid, and the tombstoned projection file is still on disk afterwards — retirement is a record, and no merge may revive the uid Refs #1400.
"""A tombstone is absorbing: no merge revives the uid (K001-UNIT-001).

wagon: govern-projection-fields | feature: mark-object-tombstone | phase: RED
WMBT: wmbt:govern-projection-fields:K001

Retirement has to survive a stale branch, and a stale branch is the *normal* case — B forked
before A retired the object and has been working ever since. If a merge can bring the uid back
by writing a live phase over the tombstone, then retirement is not a decision, it is a race.

Two claims, and the second is the quiet one: the merge is refused, **and the projection file
is still there afterwards**. A driver that resolved a resurrection by deleting the file would
have honoured the tombstone by committing exactly the deletion the tombstone exists instead of.
"""
from __future__ import annotations

from atdd.state import merge_driver, tombstone
from atdd.state.merge_driver import RULE_TOMBSTONE
from atdd.state.projection import STATE_TOMBSTONED

from ._helpers import UID_X, attributed_tombstone, document, write_document

REASON = "superseded by the projection model"


def test_k001_unit_001_red_tombstoned_object_revived(tmp_path) -> None:
    """The reviving merge is refused by uid, and the tombstoned file survives it."""
    retired = document(
        phase="GREEN",
        state=STATE_TOMBSTONED,
        tombstone=attributed_tombstone(REASON),
    )
    reviving = document(phase="SMOKE")  # a live phase, on the very same uid

    ours_path = write_document(tmp_path / f"{UID_X}.yaml", retired)
    base_path = write_document(tmp_path / "base.yaml", retired)
    theirs_path = write_document(tmp_path / "theirs.yaml", reviving)

    result = merge_driver.merge_files(base_path, ours_path, theirs_path)

    assert not result.ok
    assert result.exit_code == 1
    assert result.merged is None

    conflict = result.conflicts[0]
    assert conflict.rule == RULE_TOMBSTONE
    assert UID_X in conflict.render(), "the report names the uid that was nearly revived"
    assert "TOMBSTONED" in conflict.detail
    assert "SMOKE" in conflict.detail, "and the live phase the incoming side tried to set"

    # The tombstoned projection file still exists on disk — untouched, still the tombstone.
    assert ours_path.is_file()
    assert tombstone.is_tombstoned(
        __import__("yaml").safe_load(ours_path.read_text(encoding="utf-8"))
    )

    # The ordinary case still merges: one side retires, the other simply did not touch it.
    quiet = merge_driver.merge_object(UID_X, document(phase="GREEN"), retired, document(phase="GREEN"))
    assert quiet.ok, quiet.render()
    assert quiet.merged["state"] == STATE_TOMBSTONED
