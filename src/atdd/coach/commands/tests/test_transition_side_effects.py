"""
RED tests for #282 — atdd issue <N> --status <X> side effects.

WMBTs covered:
- wmbt:govern-lifecycle:R001 — acc:govern-lifecycle:R001-UNIT-001-manifest-status-sync
- wmbt:govern-lifecycle:R002 — acc:govern-lifecycle:R002-UNIT-001-reenter-display-only

Run: PYTHONPATH=src python3 -m pytest -q src/atdd/coach/commands/tests/test_transition_side_effects.py -v
"""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _store_status(tmp_path: Path, issue_number: int):
    from atdd.state.work_item_reader import WorkItemReader

    with WorkItemReader(control_root=tmp_path) as reader:
        return reader.status(issue_number)


def _seed_store(tmp_path: Path, issue_number: int, status: str) -> None:
    """Seed the store directly (#1270 Slice G: the manifest mirror is deleted)."""
    from atdd.state.db import connect, init_state_store
    from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
    from atdd.state.store import StateStore

    (tmp_path / ".atdd").mkdir(exist_ok=True)
    db = init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite")
    conn = connect(db)
    try:
        store = StateStore(conn)
        slug = "fix-transition-side-effects"
        store.objects.upsert(slug, WORK_ITEM_KIND, state=status,
                             data={"issue_number": issue_number, "type": "refactor"})
        store.external_refs.link(slug, GITHUB_PROVIDER, "issue", str(issue_number),
                                 data={"source": "test-seed"})
    finally:
        conn.close()


def test_r001_unit_001_update_manifest_status_writes_store_not_manifest(tmp_path):
    """R001 (#1270 Slice G): a status transition is recorded in the State Store
    (authoritative — the ``.atdd/manifest.yaml`` mirror is deleted).

    Discriminator: the store-only implementation writes the store and never
    resurrects a manifest.
    """
    from atdd.coach.commands.issue import IssueManager

    _seed_store(tmp_path, issue_number=282, status="INIT")
    manager = IssueManager(target_dir=tmp_path)

    manager._update_manifest_status(282, "PLANNED")

    # Store is authoritative and updated.
    assert _store_status(tmp_path, 282) == "PLANNED"
    # No manifest mirror is written.
    assert not (tmp_path / ".atdd" / "manifest.yaml").exists()


def test_r001_unit_001_update_manifest_status_is_noop_for_unknown_issue(tmp_path):
    """R001: calling the helper for an unregistered issue number must not crash
    and must leave the seeded work item unchanged.
    """
    from atdd.coach.commands.issue import IssueManager

    _seed_store(tmp_path, issue_number=282, status="INIT")
    manager = IssueManager(target_dir=tmp_path)

    manager._update_manifest_status(9999, "PLANNED")

    assert _store_status(tmp_path, 282) == "INIT"
    assert not (tmp_path / ".atdd" / "manifest.yaml").exists()


def test_r002_unit_001_reenter_display_only_does_not_create_branch(tmp_path, monkeypatch):
    """R002: the post-transition re-enter path must not attempt to create a worktree
    branch. It should just print the updated state.

    Currently fails: IssueLifecycle has no _reenter_display_only helper, and the existing
    transition() path calls enter() which calls _create_branch() which runs the
    worktree-ready layout check and bails with a misleading error.
    """
    from atdd.coach.commands.issue_lifecycle import IssueLifecycle

    lifecycle = IssueLifecycle(target_dir=tmp_path)

    # Fail loudly if _create_branch is ever invoked during a display-only re-enter.
    def _should_not_be_called(*args, **kwargs):
        raise AssertionError(
            "R002 violation: _create_branch invoked during display-only re-enter"
        )

    monkeypatch.setattr(lifecycle, "_create_branch", _should_not_be_called)

    def _fake_fetch_issue(issue_number):
        return {
            "number": issue_number,
            "title": "refactor(atdd): Fix Issue Transition Side Effects",
            "state": "OPEN",
            "labels": [{"name": "atdd:PLANNED"}, {"name": "atdd-issue"}],
            "body": "| Field | Value |\n|-------|-------|\n| Branch | `refactor/fix-issue-transition-side-effects` |\n",
        }

    monkeypatch.setattr(lifecycle, "_fetch_issue", _fake_fetch_issue)
    monkeypatch.setattr(lifecycle, "_fetch_sub_issues", lambda *a, **kw: [])

    rc = lifecycle._reenter_display_only(282)

    assert rc == 0
