# URN: test:govern-lifecycle:cli-readers:store-only
# Issue: #1351 (#1270 slice D — retire the manifest read-fallback)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1270 slice D — the atdd CLI-command readers read the store ONLY.

Slice B repointed these readers store-first with a manifest fallback; slice D
retires the fallback so the store is the sole read source. The "prefers store
over divergent manifest" tests still hold; the discriminating slice-D tests seed
a NON-EMPTY store (so the reader auto-import does not run) that LACKS the datum,
plus a manifest that HAS it, and assert the reader ignores the manifest —
failing on the old fallback implementation, passing once the fallback is gone.
Isolated tmp stores; independent of the ambient control-root layout.
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


def test_pr_resolve_ignores_manifest_only_slug(tmp_path):
    """Slice D — a slug only in the manifest no longer resolves (store-only).

    The store is non-empty (a different item) so no auto-import runs; the
    manifest-only slug is never seeded and must not resolve. Old (fallback)
    behaviour returned ``77``.
    """
    from atdd.coach.commands.pr import PRManager
    _seed(tmp_path, slug="other", issue_number=1)  # store has a different item
    _manifest(tmp_path, [{"slug": "only-in-manifest", "issue_number": 77}])
    mgr = PRManager(target_dir=tmp_path)
    assert mgr._resolve_via_manifest({"headRefName": "fix/only-in-manifest"}) is None


def test_pr_resolve_store_only_with_manifest_unlinked(tmp_path):
    """Slice D — the resolver works from the store with no manifest present."""
    from atdd.coach.commands.pr import PRManager
    _seed(tmp_path, slug="my-slug", issue_number=42)
    mgr = PRManager(target_dir=tmp_path)
    assert mgr._resolve_via_manifest({"headRefName": "feat/my-slug"}) == 42


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


# --- issue._manifest_train / _manifest_branch (store-only, slice D) -------- #
def test_manifest_train_store_only_ignores_manifest(tmp_path):
    """Slice D — the train read no longer falls back to the manifest.

    The store holds the issue but no train (non-empty ⇒ no auto-import); the
    manifest carries a train that must be ignored. Old (fallback) returned the
    manifest train.
    """
    from atdd.coach.commands.issue import IssueManager
    _seed(tmp_path, slug="t", issue_number=90)  # no train in the store
    _manifest(tmp_path, [{"slug": "t", "issue_number": 90, "train": "0009-from-manifest"}])
    assert IssueManager(tmp_path)._manifest_train(90) is None


def test_manifest_train_store_only_resolves_with_manifest_unlinked(tmp_path):
    """Slice D — the train resolves from the store with no manifest present."""
    from atdd.coach.commands.issue import IssueManager
    _seed(tmp_path, slug="t2", issue_number=91, train="0002-coach-drives-lifecycle")
    assert IssueManager(tmp_path)._manifest_train(91) == "0002-coach-drives-lifecycle"


def test_manifest_branch_store_only_ignores_manifest(tmp_path):
    """Slice D — the branch read no longer falls back to the manifest."""
    from atdd.coach.commands.issue import IssueManager
    _seed(tmp_path, slug="b90", issue_number=92)  # no branch in the store
    _manifest(tmp_path, [{"slug": "b90", "issue_number": 92, "branch": "feat/from-manifest"}])
    assert IssueManager(tmp_path)._manifest_branch(92) is None


def test_manifest_branch_store_only_resolves_with_manifest_unlinked(tmp_path):
    """Slice D — the branch resolves from the store with no manifest present."""
    from atdd.coach.commands.issue import IssueManager
    _seed(tmp_path, slug="b91", issue_number=93, branch="refactor/x")
    assert IssueManager(tmp_path)._manifest_branch(93) == "refactor/x"
