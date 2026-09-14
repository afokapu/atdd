# URN: test:migrate-projection-authority:migrate-store-projection:C003-UNIT-002-every-unsourced-ref-survives
# Acceptance: acc:migrate-projection-authority:C003-UNIT-002-every-unsourced-ref-survives
# WMBT: wmbt:migrate-projection-authority:C003
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: the projector merges the (github, issue) slice it sources into the subtree already present, at the (provider, ref_kind) LEAF — so a SAME-PROVIDER sibling (github.pr) and a foreign provider (jira.ticket) both survive a project+hydrate cycle. Refs #2025.
"""The merge is at the leaf, not the provider (C003-UNIT-002).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C003

`provider_seam.apply_updates` — the only sanctioned write-back into the projection — admits
ANY provider and ANY ref kind, and writes `refs[provider][ref_kind] = value`. So
`{"github": {"pr": "2028"}}` is a legal bot value, sitting under the SAME provider key the
refs table contributes `issue` to.

That makes `github.pr` the case a foreign-provider test cannot see. A projector that
rebuilds `external_refs` from the table destroys both `jira` and `github.pr`, but a test
that only checks `jira` ALSO passes when the merge happens at the provider level and quietly
drops `github.pr`. Asserting both is what makes this acceptance non-vacuous — and it is the
gap adversarial re-review opened after the first version shipped with `jira` alone.

So the merge is per `(provider, ref_kind)`: the table's slice is layered onto what is
already there, never substituted for it.

RED: the projector rebuilds the subtree from the table alone and destroys both.
"""
from __future__ import annotations

from atdd.state.projection import hydrate, project
from atdd.state.work_item_writer import create_work_item

from ._helpers import memory_store

_GITHUB, _ISSUE, _PR = "github", "issue", "pr"

#: What the extension bot legally wrote, and the table cannot source.
_BOT_WRITTEN = {_GITHUB: {_PR: "2028"}, "jira": {"ticket": "ATDD-17"}}


def test_a_ref_the_table_cannot_source_survives_a_full_cycle(tmp_path) -> None:
    """github.pr and jira.ticket both survive; github.issue is added beside them."""
    with memory_store() as (conn, store):
        item = create_work_item(
            conn, "carries-bot-refs", state="PLANNED",
            data={"title": "carries bot refs", "external_refs": dict(_BOT_WRITTEN)},
            github_number=7001,
        )

        project(store, tmp_path / "projection")
        hydrate(tmp_path / "projection", store)

        stored = store.objects.get(item.uid)
        assert stored is not None, "the object must survive the round trip"
        refs = dict(stored.data.get("external_refs") or {})
        github = dict(refs.get(_GITHUB) or {})

        assert github.get(_PR) == "2028", (
            "github.pr was destroyed. The table contributes github.issue, so a projector "
            "that rebuilds the github subtree replaces a sibling ref kind the bot is "
            "entitled to write. The merge must be at the (provider, ref_kind) leaf. "
            f"Got external_refs = {refs!r}"
        )
        assert (refs.get("jira") or {}).get("ticket") == "ATDD-17", (
            f"jira.ticket was destroyed; got external_refs = {refs!r}"
        )
        assert github.get(_ISSUE) == "7001", (
            "the table's own slice must still be projected alongside what it did not source; "
            f"got external_refs = {refs!r}"
        )
