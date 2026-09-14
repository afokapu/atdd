# URN: test:migrate-projection-authority:migrate-store-projection:E003-UNIT-001-document-names-its-issue
# Acceptance: acc:migrate-projection-authority:E003-UNIT-001-document-names-its-issue
# WMBT: wmbt:migrate-projection-authority:E003
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: the projected document carries external_refs.github.issue sourced from the external_refs TABLE, so a reconciliation workflow reading the committed projection can tell which GitHub issue a document is. Measured 0 of 746 documents carry it today. Refs #2025.
"""The projection must name its own GitHub issue (E003-UNIT-001).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:E003

The operator is adopting git as the transport to GitHub: store -> canonical YAML ->
commit -> a workflow reconciles GitHub to match. That workflow reads the committed
projection and nothing else, so a document that cannot say which issue it is gives it
nothing to reconcile.

The identity exists — 1,103 `(github, issue)` rows in the `external_refs` table — and
`external_refs` has been a `FIELD_TYPES` entry and a contract property since the spine
landed, with `writer: extension_bot` already recorded in field-ownership.yaml. The design
was anticipated. Nothing ever wired it: `build_document` reads `obj.data` alone, and no
code path writes `data["external_refs"]`.

It is about to get worse rather than better. `store_migration.DROPPED_FROM_STORE` includes
`issue_number` — ruled DROP by #1622 precisely because "the authoritative linkage is
external_refs->uid, which lives in the store". After that migration runs, the table is the
ONLY GitHub identity anywhere, and the projection reads none of it.

RED: `build_documents` emits no `external_refs` key at all, for any object.
"""
from __future__ import annotations

from atdd.state.projection import build_documents
from atdd.state.work_item_writer import create_work_item

from ._helpers import memory_store

_GITHUB, _ISSUE = "github", "issue"


def test_a_projected_document_names_the_issue_the_table_binds_it_to() -> None:
    """The document carries the ref_value the external_refs table holds for its uid."""
    with memory_store() as (conn, store):
        bound = create_work_item(
            conn, "carries-its-issue", state="PLANNED",
            data={"title": "carries its issue"}, github_number=2025,
        )
        unbound = create_work_item(
            conn, "store-only-item", state="PLANNED", data={"title": "store only"},
        )

        # The given is real: the identity is in the TABLE, which is where the
        # authoritative linkage lives and where #1622 ruled it must stay.
        assert store.external_refs.resolve(_GITHUB, _ISSUE, "2025").object_uid == bound.uid

        documents = build_documents(store)

        refs = documents[bound.uid].get("external_refs")
        assert refs is not None, (
            "the projected document carries no external_refs at all, so the committed "
            "projection cannot say which GitHub issue it is — and after the #1622 "
            "issue_number drop, nothing else in the document can either"
        )
        assert refs.get(_GITHUB, {}).get(_ISSUE) == "2025", (
            f"expected the issue the table binds ({bound.uid} -> 2025), got {refs!r}"
        )

        # An object the table binds to nothing must not invent a ref.
        unbound_refs = documents[unbound.uid].get("external_refs") or {}
        assert _ISSUE not in unbound_refs.get(_GITHUB, {}), (
            "a work item with no GitHub ref must carry no github.issue; the projector "
            "reports what the table holds and never fabricates identity"
        )
