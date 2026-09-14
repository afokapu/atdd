# URN: test:migrate-projection-authority:migrate-store-projection:E003-UNIT-004-two-issue-refs-are-refused
# Acceptance: acc:migrate-projection-authority:E003-UNIT-004-two-issue-refs-are-refused
# WMBT: wmbt:migrate-projection-authority:E003
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: an object the refs table binds to TWO GitHub issues cannot be carried by a scalar leaf, and picking one makes the emitted bytes depend on row iteration order — an I1 determinism break. The projector must refuse the run before any file is written. Refs #2025.
"""Two issues on one object is refused, not silently narrowed (E003-UNIT-004).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:E003

The refs table is `UNIQUE (provider, ref_kind, ref_value)` — NOT per object
(`migrations.py:74`). So one uid bound to two distinct GitHub issue numbers is a state the
store can hold today, and a scalar `github.issue` leaf cannot carry it.

Picking one is the tempting answer and it is the wrong one, because WHICH one survives
depends on the row order `store.external_refs.all()` happens to yield. That makes the same
logical store project different bytes on different runs — a breach of I1, the determinism
invariant the whole projection rests on, not merely a dropped row. `build_documents` already
refuses the entire corpus on the first determinism fault rather than writing a partial
projection; this is the same discipline applied to the same class of fault.

The alternative — enforcing one-issue-per-object with a `UNIQUE (object_uid, provider,
ref_kind)` — is a store-schema change that belongs to whoever owns the table, not here.

RED: the projector emits whichever ref the table yields last and drops the other in silence.
"""
from __future__ import annotations

import pytest

from atdd.state.projection import ProjectionError, build_documents
from atdd.state.work_item_writer import create_work_item

from ._helpers import memory_store

_GITHUB, _ISSUE = "github", "issue"


def test_an_object_bound_to_two_issues_refuses_the_whole_run() -> None:
    """A state the scalar cannot represent stops the projection instead of narrowing it."""
    with memory_store() as (conn, store):
        doubly_bound = create_work_item(
            conn, "bound-twice", state="PLANNED",
            data={"title": "bound twice"}, github_number=5001,
        )
        create_work_item(
            conn, "bound-once", state="PLANNED",
            data={"title": "bound once"}, github_number=5003,
        )
        # The table permits this: uniqueness is per (provider, ref_kind, ref_value).
        store.external_refs.link(doubly_bound.uid, _GITHUB, _ISSUE, "5002")

        held = {ref.ref_value for ref in store.external_refs.for_object(doubly_bound.uid)}
        assert held == {"5001", "5002"}, "the given is a genuinely doubly-bound object"

        with pytest.raises(ProjectionError) as caught:
            build_documents(store)

        message = str(caught.value)
        assert doubly_bound.uid in message, "the refusal must name the offending object"
        assert "5001" in message and "5002" in message, (
            "the refusal must name BOTH issue numbers — an operator cannot resolve the "
            f"conflict without knowing what it is between. Got: {message}"
        )
