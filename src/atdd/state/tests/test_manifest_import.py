# URN: test:state-store:manifest-import:ledger-into-store
# Issue: #1183 (#1168 Phase 4)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1183 — import `.atdd/manifest.yaml` operational state into the State Store.

Covers: each session → a `work_item` object keyed by slug (state = status, the
rest in JSON data); GitHub issue number → an external_ref projection; the
`manifest.migrated.yaml` backup; idempotent re-import; slug-less entries skipped;
a missing manifest raising; and the live `atdd state import-manifest` CLI.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from atdd.state.db import connect
from atdd.state.manifest_import import import_manifest
from atdd.state.projections import work_item_projection
from atdd.state.store import StateStore

_SRC = Path(__file__).resolve().parents[3]

_MANIFEST = {
    "version": "2.0",
    "sessions": [
        {"id": "1183", "slug": "state-store-manifest-import", "issue_number": 1183,
         "type": "implementation", "status": "RED", "train": "0002", "branch": "feat/x",
         "archived": None, "wagon": None, "feature": "feature:atdd:state-store", "file": None},
        {"id": "900", "slug": "older-thing", "issue_number": 900,
         "type": "refactor", "status": "COMPLETE"},
        {"id": "no-num", "slug": "local-only", "status": None},   # no issue_number
    ],
}


def _write_manifest(root: Path, doc=None) -> Path:
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    p = root / ".atdd" / "manifest.yaml"
    p.write_text(yaml.safe_dump(doc if doc is not None else _MANIFEST), encoding="utf-8")
    return p


def _store(db_path):
    return StateStore(connect(db_path))


def test_import_maps_sessions_to_work_items(tmp_path):
    _write_manifest(tmp_path)
    db = tmp_path / ".atdd" / "state" / "state.sqlite"

    result = import_manifest(control_root=tmp_path, db_path=db)

    assert result.imported == 3
    assert result.external_refs == 2          # two entries have issue_number
    s = _store(db)
    try:
        wi = s.objects.get("state-store-manifest-import")
        assert wi.kind == "work_item" and wi.state == "RED"
        assert wi.data["type"] == "implementation" and wi.data["feature"] == "feature:atdd:state-store"
        assert "slug" not in wi.data and "status" not in wi.data   # promoted to columns
    finally:
        s.conn.close()


def test_import_records_github_issue_as_external_ref(tmp_path):
    _write_manifest(tmp_path)
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    import_manifest(control_root=tmp_path, db_path=db)

    s = _store(db)
    try:
        ref = s.external_refs.resolve("github", "issue", "1183")
        assert ref is not None and ref.object_uid == "state-store-manifest-import"
        rows = {r.uid: r.external for r in work_item_projection(s.conn)}
        assert rows["state-store-manifest-import"] == {"github": "1183"}
        assert rows["local-only"] == {}       # no issue_number → no external ref
    finally:
        s.conn.close()


def test_import_writes_backup(tmp_path):
    manifest = _write_manifest(tmp_path)
    db = tmp_path / ".atdd" / "state" / "state.sqlite"

    result = import_manifest(control_root=tmp_path, db_path=db)

    assert result.backup_path == tmp_path / ".atdd" / "manifest.migrated.yaml"
    assert result.backup_path.read_text() == manifest.read_text()


def test_import_is_idempotent(tmp_path):
    _write_manifest(tmp_path)
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    import_manifest(control_root=tmp_path, db_path=db)
    import_manifest(control_root=tmp_path, db_path=db)   # second run

    s = _store(db)
    try:
        assert len(s.objects.list(kind="work_item")) == 3         # no duplicates
        assert len(s.external_refs.for_object("state-store-manifest-import")) == 1
    finally:
        s.conn.close()


def test_import_reflects_status_change_on_reimport(tmp_path):
    _write_manifest(tmp_path)
    db = tmp_path / ".atdd" / "state" / "state.sqlite"
    import_manifest(control_root=tmp_path, db_path=db)

    doc = dict(_MANIFEST)
    doc["sessions"] = [dict(_MANIFEST["sessions"][0], status="GREEN")] + _MANIFEST["sessions"][1:]
    _write_manifest(tmp_path, doc)
    import_manifest(control_root=tmp_path, db_path=db)

    s = _store(db)
    try:
        assert s.objects.get("state-store-manifest-import").state == "GREEN"
    finally:
        s.conn.close()


def test_import_skips_entries_without_slug(tmp_path):
    doc = {"version": "2.0", "sessions": [
        {"id": "x", "slug": "has-slug", "status": "INIT"},
        {"id": "y", "status": "INIT"},          # no slug → skipped
    ]}
    _write_manifest(tmp_path, doc)
    db = tmp_path / ".atdd" / "state" / "state.sqlite"

    result = import_manifest(control_root=tmp_path, db_path=db)

    assert result.imported == 1 and result.skipped == 1
    assert "without slug" in result.skipped_reasons[0]


def test_import_reports_duplicate_issue_numbers_first_wins(tmp_path):
    """One GitHub issue → one work item: a duplicate issue_number is reported,
    the first claimant keeps the external ref (deterministic, not silent)."""
    doc = {"version": "2.0", "sessions": [
        {"id": "a", "slug": "first-claim", "issue_number": 928, "status": "INIT"},
        {"id": "b", "slug": "second-claim", "issue_number": 928, "status": "INIT"},
    ]}
    _write_manifest(tmp_path, doc)
    db = tmp_path / ".atdd" / "state" / "state.sqlite"

    result = import_manifest(control_root=tmp_path, db_path=db)

    assert result.imported == 2 and result.external_refs == 1
    assert len(result.collisions) == 1 and "928" in result.collisions[0]
    s = _store(db)
    try:
        assert s.external_refs.resolve("github", "issue", "928").object_uid == "first-claim"
    finally:
        s.conn.close()


def test_import_missing_manifest_raises(tmp_path):
    (tmp_path / ".atdd").mkdir()
    with pytest.raises(FileNotFoundError):
        import_manifest(control_root=tmp_path, db_path=tmp_path / ".atdd" / "state" / "s.sqlite")


def test_import_manifest_cli_live(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    _write_manifest(repo)
    (repo / ".atdd" / "config.yaml").write_text("x\n", encoding="utf-8")

    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", ""),
           "HOME": str(repo), "CI": "true"}
    r = subprocess.run([sys.executable, "-m", "atdd", "state", "import-manifest", "--root", str(repo)],
                       cwd=str(repo), env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "Imported 3 work item(s)" in out
    assert (repo / ".atdd" / "manifest.migrated.yaml").is_file()
    assert (repo / ".atdd" / "state" / "state.sqlite").is_file()
