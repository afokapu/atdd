# URN: test:migrate-projection-authority:migrate-store-projection:E003-UNIT-002-hydrate-restores-the-refs-table
# Acceptance: acc:migrate-projection-authority:E003-UNIT-002-hydrate-restores-the-refs-table
# WMBT: wmbt:migrate-projection-authority:E003
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: hydrate() restores the normalized external_refs table from the projected subtree, so a peer or CI that hydrates a committed projection can resolve an issue number to a uid. Today a hydrated store holds 0 refs rows. Refs #2025.
"""The inbound half must round-trip the identity (E003-UNIT-002).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:E003

Outbound is only half the transport. Inbound, a peer's committed projection is hydrated —
and `hydrate` upserts `store.objects` ONLY. It never repopulates `external_refs`.

That is not a cosmetic gap. Both of atdd's identity-resolving gates enter through
`external_refs.resolve(github, issue, N)`:

  - `coach.gate.approval_binding` — the pre-commit registration gate
  - `coach.commands.issue_feature_binding` — behind the smoke-obligation gate

On a store hydrated from a projection, that call answers `None` for every issue in
existence, so both gates report could-not-check on everything. Measured: hydrating the
live corpus into a fresh store yields 743 objects and **0** refs rows.

RED: the refs table is empty after the hydrate, so `resolve` returns None.
"""
from __future__ import annotations

import yaml

from atdd.state.projection import PROJECTION_SUFFIX, hydrate

from ._helpers import UID_A, UID_B, memory_store

_GITHUB, _ISSUE = "github", "issue"

_DOCUMENTS = {
    UID_A: {
        "uid": UID_A, "slug": "alpha", "phase": "PLANNED", "state": "ACTIVE",
        "owner_actor": "atdd:unattributed", "title": "Alpha",
        "external_refs": {_GITHUB: {_ISSUE: "4011"}},
    },
    UID_B: {
        "uid": UID_B, "slug": "beta", "phase": "RED", "state": "ACTIVE",
        "owner_actor": "atdd:unattributed", "title": "Beta",
        "external_refs": {_GITHUB: {_ISSUE: "4012"}},
    },
}


def _write_projection(directory) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for uid, document in _DOCUMENTS.items():
        (directory / f"{uid}{PROJECTION_SUFFIX}").write_text(
            yaml.safe_dump(document, sort_keys=True, default_flow_style=False),
            encoding="utf-8",
        )


def test_hydrate_rebuilds_the_external_refs_table(tmp_path) -> None:
    """A store hydrated from the projection alone can resolve an issue number to its uid."""
    projection_dir = tmp_path / "projection"
    _write_projection(projection_dir)

    with memory_store() as (_conn, store):
        hydrate(projection_dir, store)

        assert len(store.objects.list(kind="work_item")) == 2, "objects must still hydrate"

        for uid, issue in ((UID_A, "4011"), (UID_B, "4012")):
            ref = store.external_refs.resolve(_GITHUB, _ISSUE, issue)
            assert ref is not None, (
                f"issue {issue} resolves to nothing after hydrate — hydrate rebuilds "
                "store.objects only and never repopulates external_refs, so every gate "
                "that enters through resolve(github, issue, N) answers could-not-check"
            )
            assert ref.object_uid == uid, (
                f"issue {issue} must resolve to {uid}, got {ref.object_uid}"
            )

        assert len(store.external_refs.for_object(UID_A)) == 1, (
            "exactly one ref per document that named one — no duplicates from the restore"
        )
