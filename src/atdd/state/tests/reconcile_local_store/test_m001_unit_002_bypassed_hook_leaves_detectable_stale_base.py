# URN: test:reconcile-local-store:trigger-head-hooks:M001-UNIT-002-bypassed-hook-leaves-detectable-stale-base
# Acceptance: acc:reconcile-local-store:M001-UNIT-002-bypassed-hook-leaves-detectable-stale-base
# WMBT: wmbt:reconcile-local-store:M001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: when the hooks are absent or skipped, HEAD advances past store_base_commit and that staleness is DETECTED and reported against HEAD, directing the operator to reconcile — hook absence is missing convenience, never missing authority. Refs #1400.
"""A bypassed hook is detected, not tolerated (M001-UNIT-002).

wagon: reconcile-local-store | feature: trigger-head-hooks | phase: RED
WMBT: wmbt:reconcile-local-store:M001

Client hooks are convenience, never authority (spec §9). That claim only holds if
bypassing one is *harmless*, and it is only harmless if it is *visible*: a store whose
anchor has fallen behind HEAD is quietly wrong — it will happily answer questions using
public state that the shared truth has already moved past.

So freshness is checked from the store's own metadata, not from the hook's presence. A
checkout with no ATDD hooks installed at all still detects its own staleness — which is
exactly what makes the hook optional rather than load-bearing. Refs #1400.
"""
from __future__ import annotations

from atdd.state.reconcile import freshness, hydrate_store, reconcile

from ._helpers import UID_A, checkout, commit_all, document, head, write_projection


def test_m001_unit_002_bypassed_hook_leaves_detectable_stale_base(tmp_path) -> None:
    """HEAD moving without the hook leaves a stale base, and freshness reports it."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED")])
    base = commit_all(repo, "base projection")
    hydrate_store(repo)

    # No ATDD hooks are installed in this checkout at all.
    assert not (repo / ".git" / "hooks" / "post-merge").exists()
    assert not (repo / ".atdd" / "hooks").exists()

    fresh = freshness(repo)
    assert fresh.stale is False
    assert fresh.base_commit == base == fresh.head

    # HEAD advances with no hook to notice — a pull, a rebase, a checkout, whatever.
    write_projection(repo, [document(UID_A, phase="GREEN")])
    moved = commit_all(repo, "peer work; no hook ran")
    assert moved == head(repo) != base

    stale = freshness(repo)

    # The stale store_base_commit is detected and reported against HEAD.
    assert stale.stale is True
    assert stale.base_commit == base       # the store is still anchored to the OLD commit
    assert stale.head == moved             # while HEAD has moved on

    rendered = stale.render()
    assert "STALE" in rendered
    assert base[:12] in rendered
    assert moved[:12] in rendered

    # The operator is directed to run `atdd state reconcile`.
    assert "atdd state reconcile" in rendered
    assert "hook" in rendered  # it names WHY the store is behind

    # Hook absence is missing convenience, never missing authority: running reconcile
    # by hand — with no hook anywhere — restores the store completely.
    reconcile(repo)
    assert freshness(repo).stale is False
    assert freshness(repo).base_commit == moved
