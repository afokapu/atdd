# URN: test:project-shared-state:project-store:E001-UNIT-002-emits-canonical-per-uid-yaml
# Acceptance: acc:project-shared-state:E001-UNIT-002-emits-canonical-per-uid-yaml
# WMBT: wmbt:project-shared-state:E001
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: project(store) emits one canonical per-uid YAML per object — sorted keys, sorted sequences, and bytes that do not move with store insertion order. Refs #1433.
"""One canonical per-uid document per object, in a fixed order (E001-UNIT-002).

wagon: project-shared-state | feature: project-store | phase: GREEN
WMBT: wmbt:project-shared-state:E001

The store's row order is an implementation detail of SQLite; the projection's byte
order is a contract with every peer and with CI. Refs #1433 / #1400.
"""
from __future__ import annotations

import yaml

from atdd.state.projection import project
from atdd.state.work_item_writer import mint_work_item, update_work_item

from ._helpers import memory_store, two_work_items


def _keys_in_file_order(path) -> list:
    """The mapping keys in the order the file actually emits them."""
    return [
        line.split(":", 1)[0]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith((" ", "-"))
    ]


def test_e001_unit_002_emits_canonical_per_uid_yaml(tmp_path) -> None:
    """Each object becomes one <uid>.yaml with canonical key and sequence order."""
    with memory_store() as (conn, store):
        zeta_uid, alpha_uid = two_work_items(conn)
        result = project(store, tmp_path / "projection")

        # Each object is written to <uid>.yaml carrying the projection fields.
        document = yaml.safe_load(result.files[zeta_uid].read_text(encoding="utf-8"))
        assert document["uid"] == zeta_uid
        assert document["slug"] == "zeta-feature"
        assert document["phase"] == "GREEN"
        assert document["body"] == "zeta body"
        assert document["train"] == "train:t:z"
        assert document["wmbts"] == ["wmbt:w:C001", "wmbt:w:E002"]

        # Mapping keys are emitted in a fixed canonical (sorted) order, and the
        # wmbts sequence is emitted sorted — not in the order it was written.
        keys = _keys_in_file_order(result.files[zeta_uid])
        assert keys == sorted(keys)
        assert "wmbts" in keys

        # Insertion order of the store rows changes no emitted byte: a store built
        # in the opposite order yields the same bytes for the same logical object.
        original = {uid: path.read_bytes() for uid, path in result.files.items()}

    with memory_store() as (conn, store):
        alpha = mint_work_item(
            conn, slug="alpha-feature", owner_actor="dev-a", title="Alpha",
            body="alpha body", phase="PLANNED",
        )
        zeta = mint_work_item(
            conn, slug="zeta-feature", owner_actor="dev-b", title="Zeta",
            body="zeta body", phase="GREEN",
        )
        update_work_item(conn, alpha.uid, {"wmbts": ["wmbt:w:E001"], "train": "train:t:a"})
        update_work_item(
            conn, zeta.uid, {"wmbts": ["wmbt:w:C001", "wmbt:w:E002"], "train": "train:t:z"},
        )
        reordered = project(store, tmp_path / "reordered")

    # The uids differ (a fresh mint), so compare the bytes with identity factored out.
    def _without_uid(blob: bytes, uid: str) -> bytes:
        return blob.replace(uid.encode("utf-8"), b"<uid>")

    assert _without_uid(original[zeta_uid], zeta_uid) == _without_uid(
        reordered.files[zeta.uid].read_bytes(), zeta.uid
    )
    assert _without_uid(original[alpha_uid], alpha_uid) == _without_uid(
        reordered.files[alpha.uid].read_bytes(), alpha.uid
    )
