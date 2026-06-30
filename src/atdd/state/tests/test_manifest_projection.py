# URN: test:state-store:manifest-projection:store-to-manifest-roundtrip
# Issue: #1203 (#1168 Phase 4 cutover, Phase 2 authoritative writes)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1203 Phase 2 — regenerate `.atdd/manifest.yaml` as a State Store projection.

The store is authoritative; the manifest is a generated dump. These tests prove:

- **round-trip**: import a manifest → project it back → the work-item state
  (slug/status/issue_number + data fields) is preserved (the inverse of #1183);
- **byte-stability**: re-projecting an unchanged store yields identical YAML
  (no merge churn) — including stable session ordering and key order;
- **store is the source**: a store-only edit shows up in the projected manifest
  without touching the old manifest text;
- **top-level preserved**: `version` / `created` carry forward unchanged;
- **issue number from the external_ref**: the GitHub issue number is taken from
  the authoritative external_ref projection.
"""
from __future__ import annotations

import yaml

from atdd.state.db import connect
from atdd.state.manifest_import import import_manifest
from atdd.state.manifest_projection import (
    build_manifest_doc,
    write_manifest_projection,
)
from atdd.state.store import StateStore

_MANIFEST = {
    "version": "2.0",
    "created": "2026-06-22",
    "sessions": [
        {
            "id": "1203", "slug": "state-store-authoritative", "file": None,
            "issue_number": 1203, "type": "implementation", "status": "GREEN",
            "created": "2026-06-22", "archived": None, "train": "0002",
            "branch": "feat/x", "feature": "feature:atdd:state-store",
        },
        {
            "id": "900", "slug": "older-thing", "issue_number": 900,
            "type": "refactor", "status": "COMPLETE",
        },
        {"id": "no-num", "slug": "local-only", "status": None},  # no issue_number
    ],
}


def _write_manifest(root, doc=None):
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    path = root / ".atdd" / "manifest.yaml"
    path.write_text(yaml.safe_dump(doc if doc is not None else _MANIFEST), encoding="utf-8")
    return path


def _by_slug(sessions):
    return {s["slug"]: s for s in sessions}


def test_roundtrip_preserves_work_item_state(tmp_path):
    manifest = _write_manifest(tmp_path)
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    import_manifest(control_root=tmp_path, db_path=db)

    write_manifest_projection(control_root=tmp_path, db_path=db, manifest_path=manifest)
    projected = yaml.safe_load(manifest.read_text())

    orig = _by_slug(_MANIFEST["sessions"])
    proj = _by_slug(projected["sessions"])
    assert set(proj) == set(orig)
    for slug, o in orig.items():
        p = proj[slug]
        assert p["status"] == o["status"]
        assert p.get("issue_number") == o.get("issue_number")
        assert p.get("train") == o.get("train")
        assert p.get("branch") == o.get("branch")


def test_top_level_keys_preserved(tmp_path):
    manifest = _write_manifest(tmp_path)
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    import_manifest(control_root=tmp_path, db_path=db)

    write_manifest_projection(control_root=tmp_path, db_path=db, manifest_path=manifest)
    projected = yaml.safe_load(manifest.read_text())
    assert projected["version"] == "2.0"
    assert projected["created"] == "2026-06-22"


def test_reprojection_is_byte_stable(tmp_path):
    manifest = _write_manifest(tmp_path)
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    import_manifest(control_root=tmp_path, db_path=db)

    write_manifest_projection(control_root=tmp_path, db_path=db, manifest_path=manifest)
    first = manifest.read_text()
    write_manifest_projection(control_root=tmp_path, db_path=db, manifest_path=manifest)
    second = manifest.read_text()
    assert first == second  # no churn on an unchanged store


def test_sessions_sorted_by_issue_then_slug(tmp_path):
    manifest = _write_manifest(tmp_path)
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    import_manifest(control_root=tmp_path, db_path=db)
    write_manifest_projection(control_root=tmp_path, db_path=db, manifest_path=manifest)
    projected = yaml.safe_load(manifest.read_text())
    nums = [s.get("issue_number") for s in projected["sessions"]]
    # numbered issues ascending first, the slug-only (None) entry sorts last.
    assert nums == [900, 1203, None]


def test_store_edit_shows_in_projection(tmp_path):
    manifest = _write_manifest(tmp_path)
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    import_manifest(control_root=tmp_path, db_path=db)

    conn = connect(db)
    try:
        StateStore(conn).objects.set_state("state-store-authoritative", "SMOKE")
    finally:
        conn.close()

    write_manifest_projection(control_root=tmp_path, db_path=db, manifest_path=manifest)
    projected = yaml.safe_load(manifest.read_text())
    assert _by_slug(projected["sessions"])["state-store-authoritative"]["status"] == "SMOKE"


def test_issue_number_taken_from_external_ref(tmp_path):
    manifest = _write_manifest(tmp_path)
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    import_manifest(control_root=tmp_path, db_path=db)

    conn = connect(db)
    try:
        doc = build_manifest_doc(conn, base_doc={"version": "2.0"})
    finally:
        conn.close()
    entry = _by_slug(doc["sessions"])["state-store-authoritative"]
    assert entry["issue_number"] == 1203
    assert isinstance(entry["issue_number"], int)
