# URN: test:govern-lifecycle:runtime-graph:store-first-issue-wagon-map
# Issue: #1318 (#1270 slice A — decommission the manifest mirror)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1270 slice A — runtime graph ``issue_wagon_map`` reads the State Store first.

``issue_wagon_map`` drives wave planning by mapping issue → wagon. It was
manifest-only; #1203 made the store authoritative. The discriminating test
seeds the store and a *divergent* manifest and asserts the store wins — failing
on the old manifest-only implementation. The manifest fallback is retained when
the store carries no wagons.
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


def test_issue_wagon_map_falls_back_to_manifest_when_store_has_no_wagons(tmp_path):
    """A store with no wagons (e.g. writer-populated) falls back to the manifest."""
    # Store holds the issue but no wagon at all → store map empty → manifest wins.
    _seed_store(tmp_path, slug="b", issue_number=7)
    _write_manifest(tmp_path, [{"issue_number": 7, "slug": "b", "wagon": "define-plans"}])
    assert issue_wagon_map(tmp_path) == {7: "define-plans"}
