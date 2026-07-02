# URN: test:govern-lifecycle:branch-gate:store-backed-is-registered
# Issue: #1323 (#1270 slice C — decommission the manifest mirror)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1270 slice C — store-backed branch-registration check.

`IssueManager.branch_is_registered` is the store-first replacement for the
pre-commit hook's `grep "slug:" .atdd/manifest.yaml`. It resolves branch → slug
and checks the State Store first, then the manifest mirror. Isolated tmp stores.
"""
from __future__ import annotations

import yaml

from atdd.coach.commands.issue import IssueManager
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.store import StateStore


def _root(tmp_path):
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n")  # control-root marker
    return tmp_path


def _seed_store(tmp_path, slug):
    db = init_state_store(start=tmp_path)
    conn = connect(db)
    try:
        StateStore(conn).objects.upsert(slug, WORK_ITEM_KIND, state="RED", data={"issue_number": 1})
        conn.commit()
    finally:
        conn.close()


def _write_manifest(tmp_path, slugs):
    (tmp_path / ".atdd" / "manifest.yaml").write_text(
        yaml.safe_dump({"sessions": [{"slug": s, "issue_number": i} for i, s in enumerate(slugs, 1)]})
    )


def test_registered_via_store(tmp_path):
    root = _root(tmp_path)
    _seed_store(root, "my-thing")
    # no manifest at all → answer must come from the store
    assert IssueManager(root).branch_is_registered("refactor/my-thing") is True


def test_store_wins_over_absent_manifest_entry(tmp_path):
    """Store registers the slug even though the manifest omits it (store-first)."""
    root = _root(tmp_path)
    _seed_store(root, "store-only")
    _write_manifest(root, ["something-else"])  # manifest does NOT list store-only
    assert IssueManager(root).branch_is_registered("feat/store-only") is True


def test_unregistered_when_managed(tmp_path):
    """Managed repo (store has items) but slug absent everywhere → not registered."""
    root = _root(tmp_path)
    _seed_store(root, "other-thing")
    _write_manifest(root, ["other-thing"])
    assert IssueManager(root).branch_is_registered("feat/never-registered") is False


def test_registered_via_manifest_fallback(tmp_path):
    """Empty store, manifest carries the slug → registered (fallback)."""
    root = _root(tmp_path)
    _write_manifest(root, ["manifest-thing"])
    assert IssueManager(root).branch_is_registered("fix/manifest-thing") is True


def test_unmanaged_repo_not_blocked(tmp_path):
    """Empty store and no manifest → nothing to check → do not block (True)."""
    root = _root(tmp_path)
    assert IssueManager(root).branch_is_registered("feat/whatever") is True


def test_slug_derivation_strips_prefix(tmp_path):
    """Only the post-prefix slug is matched (feat/x → x); a bare name works too."""
    root = _root(tmp_path)
    _seed_store(root, "bare-name")
    assert IssueManager(root).branch_is_registered("bare-name") is True
    assert IssueManager(root).branch_is_registered("feat/bare-name") is True
