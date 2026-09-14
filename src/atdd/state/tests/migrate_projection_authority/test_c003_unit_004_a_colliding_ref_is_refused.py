# URN: test:migrate-projection-authority:migrate-store-projection:C003-UNIT-004-a-colliding-ref-is-refused
# Acceptance: acc:migrate-projection-authority:C003-UNIT-004-a-colliding-ref-is-refused
# WMBT: wmbt:migrate-projection-authority:C003
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: an inbound projection binding an issue the LOCAL store already binds elsewhere must be refused before any write — link() is ON CONFLICT DO UPDATE SET object_uid, so the existing binding is silently re-pointed. This is the object conflict the train is named for. Refs #2025.
"""A collision with the local store is refused, not silently resolved (C003-UNIT-004).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C003

Two peers, two branches, one issue number bound to different uids. That is not a hypothetical
— it is the object conflict `train:object-conflict-resolution` exists to resolve, and it is
what an inbound ingest will meet the first time two people work the same issue.

`ExternalRefStore.link` is `ON CONFLICT(provider, ref_kind, ref_value) DO UPDATE SET
object_uid=excluded.object_uid`. Last writer wins, with no signal. A live binding is
re-pointed at a different object and nothing anywhere reports it.

Checking uniqueness WITHIN the incoming document set is not enough and was the first
version's mistake: the collision that actually happens is against the refs the LOCAL STORE
ALREADY HOLDS. So the check runs against both, before the first write, matching
`build_documents`' refuse-before-any-write discipline.

RED: the binding is silently re-pointed and the hydrate reports success.
"""
from __future__ import annotations

import pytest
import yaml

from atdd.state.projection import PROJECTION_SUFFIX, ProjectionError, hydrate
from atdd.state.work_item_writer import create_work_item

from ._helpers import UID_A, memory_store

_GITHUB, _ISSUE = "github", "issue"
_CONTESTED = "9001"


def _write_peer_projection(directory, uid: str) -> None:
    """A peer's committed projection, binding the contested issue to ITS uid."""
    directory.mkdir(parents=True, exist_ok=True)
    document = {
        "uid": uid, "slug": "peer-item", "phase": "PLANNED", "state": "ACTIVE",
        "owner_actor": "atdd:unattributed", "title": "The peer's work item",
        "external_refs": {_GITHUB: {_ISSUE: _CONTESTED}},
    }
    (directory / f"{uid}{PROJECTION_SUFFIX}").write_text(
        yaml.safe_dump(document, sort_keys=True, default_flow_style=False), encoding="utf-8",
    )


def test_an_inbound_ref_colliding_with_a_local_binding_is_refused(tmp_path) -> None:
    """The hydrate refuses naming both uids, and writes nothing."""
    with memory_store() as (conn, store):
        mine = create_work_item(
            conn, "my-work-item", state="PLANNED",
            data={"title": "mine"}, github_number=int(_CONTESTED),
        )
        assert store.external_refs.resolve(_GITHUB, _ISSUE, _CONTESTED).object_uid == mine.uid

        projection_dir = tmp_path / "projection"
        _write_peer_projection(projection_dir, UID_A)

        objects_before = {o.uid for o in store.objects.list(kind="work_item")}

        with pytest.raises(ProjectionError) as caught:
            hydrate(projection_dir, store)

        message = str(caught.value)
        assert _CONTESTED in message, "the refusal must name the contested issue number"
        assert mine.uid in message and UID_A in message, (
            "the refusal must name BOTH claimants — the operator resolving this needs to "
            f"know which two objects are in conflict. Got: {message}"
        )

        still = store.external_refs.resolve(_GITHUB, _ISSUE, _CONTESTED)
        assert still.object_uid == mine.uid, (
            "the local binding was re-pointed. link() is DO UPDATE SET object_uid, so a "
            "collision silently reassigns a live issue->uid binding"
        )
        assert {o.uid for o in store.objects.list(kind="work_item")} == objects_before, (
            "a refused hydrate must write nothing at all, not even the objects it "
            "processed before reaching the collision"
        )
