# URN: test:govern-lifecycle:runtime-graph:store-only-issue-wagon-map
# Issue: #1351 (#1270 slice D — retire the manifest read-fallback)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1270 slice D — runtime graph ``issue_wagon_map`` reads the State Store ONLY.

``issue_wagon_map`` drives wave planning by mapping issue → wagon. Slice A made
it store-first with a manifest fallback; slice D retires that fallback so the
store is the sole read source (the manifest is now only the store's cold-start
seed, read by nothing). The discriminating test seeds a NON-EMPTY store (so the
reader's auto-import does not run) lacking a wagon, plus a manifest that DOES
carry the wagon, and asserts the reader ignores the manifest — failing on the
old fallback implementation, passing once the fallback is gone.
"""
from __future__ import annotations

import yaml

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore
from atdd.coach.runtime.graph import issue_wagon_map


def _seed_store(root, *, slug, issue_number, wagon=None):
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    marker = root / ".atdd" / "config.yaml"
    if not marker.exists():
        marker.write_text("version: '1.0'\n", encoding="utf-8")  # Control Root marker
    db = init_state_store(start=root)
    conn = connect(db)
    try:
        store = StateStore(conn)
        data = {"issue_number": issue_number}
        if wagon:
            data["wagon"] = wagon
        store.objects.upsert(slug, WORK_ITEM_KIND, state="PLANNED", data=data)
        store.external_refs.link(
            slug, GITHUB_PROVIDER, "issue", str(issue_number), data={}
        )
    finally:
        conn.close()


def _write_manifest(root, sessions):
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    path = root / ".atdd" / "manifest.yaml"
    path.write_text(yaml.safe_dump({"version": "2.0", "sessions": sessions}), encoding="utf-8")
    return path


def test_issue_wagon_map_prefers_store_over_divergent_manifest(tmp_path):
    """The map is built from the store when it carries wagons, not the manifest."""
    _seed_store(tmp_path, slug="a", issue_number=42, wagon="govern-lifecycle")
    _write_manifest(
        tmp_path,
        [{"issue_number": 42, "slug": "a", "wagon": "author-plan-substrate"}],
    )
    assert issue_wagon_map(tmp_path) == {42: "govern-lifecycle"}


def test_issue_wagon_map_ignores_manifest_when_store_has_no_wagons(tmp_path):
    """Slice D — a store with no wagons no longer falls back to the manifest.

    The store is non-empty (holds the issue) so the reader's cold-start
    auto-import does not run; the manifest's wagon is therefore never seeded and
    must be ignored. Old (fallback) behaviour returned ``{7: "define-plans"}``.
    """
    _seed_store(tmp_path, slug="b", issue_number=7)
    _write_manifest(tmp_path, [{"issue_number": 7, "slug": "b", "wagon": "define-plans"}])
    assert issue_wagon_map(tmp_path) == {}


def test_issue_wagon_map_store_only_with_manifest_unlinked(tmp_path):
    """Slice D — the map resolves from the store with no manifest present at all."""
    _seed_store(tmp_path, slug="c", issue_number=9, wagon="govern-lifecycle")
    # No manifest written.
    assert issue_wagon_map(tmp_path) == {9: "govern-lifecycle"}
