# URN: test:migrate-projection-authority:migrate-store-projection:C002-UNIT-001-projection-round-trips
# Acceptance: acc:migrate-projection-authority:C002-UNIT-001-projection-round-trips
# WMBT: wmbt:migrate-projection-authority:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: project(hydrate(p)) must equal p byte for byte. A projection that cannot reproduce itself is a snapshot, not shared state — and today none can be produced from a store the live writer filled. Refs #1622.

"""The committed projection must reproduce itself byte for byte (C002-UNIT-001).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C002

Round-tripping is what separates shared state from a snapshot. If hydrating the
committed projection and re-projecting yields different bytes, then two developers
who both hydrate it hold different truths, and the merge driver is adjudicating
between artifacts that never agreed in the first place.

This is also the M8 exit criterion that fails today, in its mechanical form:
`atdd state cutover` reports `projection-is-shared-state` unmet because no committed
projection exists at all.

RED: the round trip cannot even begin. `project()` refuses the store the live writer
filled — the contract rejects every object's uid and its absent `owner_actor` — so
there is no `p` to hydrate. The failure below is that refusal, raised out of
`project`, not a missing fixture.
"""
from __future__ import annotations

import pytest

from atdd.state.projection import (
    ProjectionSchemaError,
    canonical_bytes,
    hydrate,
    project,
    read_projection,
)
from atdd.state.work_item_writer import create_work_item

from ._helpers import memory_store


def test_projecting_hydrating_and_reprojecting_is_byte_identical(tmp_path) -> None:
    """project(hydrate(p)) == p, byte for byte, over a store the live writer filled."""
    out_dir = tmp_path / "projection"

    with memory_store() as (conn, store):
        for slug in ("alpha-work-item", "beta-work-item"):
            create_work_item(conn, slug, state="PLANNED", data={"title": slug})

        try:
            first = project(store, out_dir)
        except ProjectionSchemaError as exc:  # pragma: no cover - the RED path
            pytest.fail(
                "no projection can be produced from the store, so it can never be "
                f"round-tripped or committed as shared state: {exc}"
            )

        original = {
            path.name: path.read_bytes() for path in sorted(out_dir.glob("*.yaml"))
        }
        assert original, "a projection with no files cannot be shared state"

    documents = read_projection(out_dir)

    with memory_store() as (_conn, store2):
        hydrate(out_dir, store2)
        second = project(store2, out_dir)

        reproduced = {
            path.name: path.read_bytes() for path in sorted(out_dir.glob("*.yaml"))
        }

    assert reproduced == original, "re-projection must reproduce the bytes exactly"
    assert second.digest == first.digest, "the projection digest must survive the round trip"

    for uid, document in documents.items():
        assert canonical_bytes(document) == original[f"{uid}.yaml"]
