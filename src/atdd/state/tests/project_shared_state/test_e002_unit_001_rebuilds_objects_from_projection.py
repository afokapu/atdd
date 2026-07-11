# URN: test:project-shared-state:hydrate-projection:E002-UNIT-001-rebuilds-objects-from-projection
# Acceptance: acc:project-shared-state:E002-UNIT-001-rebuilds-objects-from-projection
# WMBT: wmbt:project-shared-state:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: hydrate(projection) reconstructs every public field the projection documents carry — uid, slug, phase, body, train and wmbts all round-trip into an empty store. Refs #1433.
"""hydrate(projection) is lossless (E002-UNIT-001).

wagon: project-shared-state | feature: hydrate-projection | phase: RED
WMBT: wmbt:project-shared-state:E002

Hydration is what lets a peer — or CI, which has no store at all — rebuild shared
state from the committed YAML alone. If it lost a field, the round-trip identity
CI depends on would silently fail on that field forever. Refs #1433 / #1400.
"""
from __future__ import annotations

from atdd.state.projection import hydrate

from ._helpers import memory_store

_DOCS = {
    "wi_01HF7YAT00M78607F000000011": {
        "uid": "wi_01HF7YAT00M78607F000000011",
        "slug": "feature-x",
        "title": "Feature X",
        "phase": "PLANNED",
        "state": "ACTIVE",
        "owner_actor": "dev-a",
        "body": "the body of feature x",
        "train": "train:commons:spine",
        "wmbts": ["wmbt:w:C001", "wmbt:w:E001"],
    },
    "wi_01HF7YAT00M78607F000000012": {
        "uid": "wi_01HF7YAT00M78607F000000012",
        "slug": "feature-y",
        "phase": "RED",
        "state": "ACTIVE",
        "owner_actor": "dev-b",
        "body": "the body of feature y",
        "train": None,
        "wmbts": [],
    },
}


def _write_projection(projection_dir, documents):
    import yaml

    projection_dir.mkdir(parents=True, exist_ok=True)
    for uid, document in documents.items():
        (projection_dir / f"{uid}.yaml").write_text(
            yaml.safe_dump(document, sort_keys=True), encoding="utf-8",
        )
    return projection_dir


def test_e002_unit_001_rebuilds_objects_from_projection(tmp_path) -> None:
    """Both objects land in the store keyed by uid, with every field intact."""
    projection_dir = _write_projection(tmp_path / "projection", _DOCS)

    with memory_store() as (conn, store):
        assert store.objects.list() == [] or all(
            o.kind != "work_item" for o in store.objects.list()
        )

        result = hydrate(projection_dir, store)
        assert result.hydrated == 2

        for uid, document in _DOCS.items():
            # Both objects exist in the store keyed by uid.
            obj = store.objects.get(uid)
            assert obj is not None, f"{uid} was not hydrated"

            # uid, slug, phase, body, train and wmbts round-trip with the YAML's values.
            assert obj.uid == document["uid"]
            assert obj.state == document["phase"]
            assert obj.data["slug"] == document["slug"]
            assert obj.data["body"] == document["body"]
            assert obj.data["train"] == document["train"]
            assert obj.data["wmbts"] == document["wmbts"]
