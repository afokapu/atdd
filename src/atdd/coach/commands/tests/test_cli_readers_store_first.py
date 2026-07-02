# URN: test:govern-lifecycle:cli-readers:store-first
# Issue: #1320 (#1270 slice B — decommission the manifest mirror)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1270 slice B — the atdd CLI-command readers read the store first.

Discriminating tests seed the store and a DIVERGENT manifest for the same
issue/slug, then assert the reader returns the STORE value — failing on the
manifest-only implementations, passing once repointed store-first with manifest
fallback. Isolated tmp stores; independent of the ambient control-root layout.
"""
from __future__ import annotations

import yaml

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore


def _seed(root, *, slug, issue_number, status="PLANNED", **data):
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    marker = root / ".atdd" / "config.yaml"
    if not marker.exists():
        marker.write_text("version: '1.0'\n", encoding="utf-8")  # Control Root marker
    db = init_state_store(start=root)
    conn = connect(db)
    try:
        s = StateStore(conn)
        s.objects.upsert(slug, WORK_ITEM_KIND, state=status,
                         data={"issue_number": issue_number, **data})
        s.external_refs.link(slug, GITHUB_PROVIDER, "issue", str(issue_number), data={})
    finally:
        conn.close()


def _manifest(root, sessions):
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    (root / ".atdd" / "manifest.yaml").write_text(
        yaml.safe_dump({"version": "2.0", "sessions": sessions}), encoding="utf-8")


# --- pr._resolve_via_manifest (branch slug → issue_number) ----------------- #
def test_pr_resolve_via_store_over_divergent_manifest(tmp_path):
    from atdd.coach.commands.pr import PRManager
    _seed(tmp_path, slug="my-slug", issue_number=42)
    _manifest(tmp_path, [{"slug": "my-slug", "issue_number": 999}])  # divergent
    mgr = PRManager(target_dir=tmp_path)
    assert mgr._resolve_via_manifest({"headRefName": "feat/my-slug"}) == 42


def test_pr_resolve_falls_back_to_manifest(tmp_path):
    """No store link for the slug → manifest mirror still resolves it."""
    from atdd.coach.commands.pr import PRManager
    _seed(tmp_path, slug="other", issue_number=1)  # store has a different item
    _manifest(tmp_path, [{"slug": "only-in-manifest", "issue_number": 77}])
    mgr = PRManager(target_dir=tmp_path)
    assert mgr._resolve_via_manifest({"headRefName": "fix/only-in-manifest"}) == 77


# --- pr._find_issue_in_manifest (type) ------------------------------------- #
def test_pr_find_issue_type_from_store(tmp_path):
    from atdd.coach.commands.pr import PRManager
    _seed(tmp_path, slug="x", issue_number=7, type="refactor")
    _manifest(tmp_path, [{"slug": "x", "issue_number": 7, "type": "implementation"}])
    mgr = PRManager(target_dir=tmp_path)
    assert (mgr._find_issue_in_manifest(7) or {}).get("type") == "refactor"


# --- branch._find_issue (slug + type) -------------------------------------- #
def test_branch_find_issue_from_store(tmp_path):
    from atdd.coach.commands.branch import BranchManager
    _seed(tmp_path, slug="the-slug", issue_number=55, type="refactor")
    _manifest(tmp_path, [{"slug": "WRONG", "issue_number": 55, "type": "implementation"}])
    entry = BranchManager(target_dir=tmp_path)._find_issue(55)
    assert entry is not None
    assert entry["slug"] == "the-slug"
    assert entry.get("type") == "refactor"


# --- issue.sync_wmbts (wagon + feature) ------------------------------------ #
def test_sync_wmbts_reads_wagon_feature_from_store(tmp_path):
    from atdd.coach.commands.issue import IssueManager
    _seed(tmp_path, slug="w", issue_number=88,
          wagon="govern-lifecycle", feature="feature:govern-lifecycle:x")
    _manifest(tmp_path, [{"slug": "w", "issue_number": 88,
                          "wagon": "author-plan-substrate", "feature": "feature:other:y"}])
    mgr = IssueManager(tmp_path)
    captured = {}
    mgr._discover_wmbts_from_feature = lambda wagon, feature: captured.update(
        wagon=wagon, feature=feature) or []
    mgr.sync_wmbts(88)
    assert captured.get("wagon") == "govern-lifecycle"
    assert captured.get("feature") == "feature:govern-lifecycle:x"
