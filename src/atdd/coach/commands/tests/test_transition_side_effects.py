"""
RED tests for #282 — atdd issue <N> --status <X> side effects.

WMBTs covered:
- wmbt:govern-lifecycle:R001 — acc:govern-lifecycle:R001-UNIT-001-manifest-status-sync
- wmbt:govern-lifecycle:R002 — acc:govern-lifecycle:R002-UNIT-001-reenter-display-only

Run: PYTHONPATH=src python3 -m pytest -q src/atdd/coach/commands/tests/test_transition_side_effects.py -v
"""
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.platform]


def _store_status(tmp_path: Path, issue_number: int):
    from atdd.state.work_item_reader import WorkItemReader

    with WorkItemReader(control_root=tmp_path) as reader:
        return reader.status(issue_number)


def _write_manifest(tmp_path: Path, issue_number: int, status: str) -> Path:
    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()
    manifest_path = atdd_dir / "manifest.yaml"
    manifest_path.write_text(
        "version: '2.0'\n"
        "created: '2026-04-14'\n"
        "sessions:\n"
        f"  - id: '{issue_number}'\n"
        "    slug: fix-transition-side-effects\n"
        "    file: null\n"
        f"    issue_number: {issue_number}\n"
        "    type: refactor\n"
        f"    status: {status}\n"
        "    created: '2026-04-14'\n"
        "    archived: null\n"
    )
    return manifest_path


def test_r001_unit_001_update_manifest_status_writes_store_not_manifest(tmp_path):
    """R001 (#1270 slice F): a status transition is recorded in the State Store;
    the ``.atdd/manifest.yaml`` mirror write is retired (the store is
    authoritative — slices A–E migrated every reader to it).

    Discriminator: the old mirror implementation rewrote the manifest session's
    status; the store-only implementation leaves the manifest untouched.
    """
    from atdd.coach.commands.issue import IssueManager

    # The manifest seeds the store once via the reader's cold-start auto-import;
    # the transition then updates the store (authoritative).
    manifest_path = _write_manifest(tmp_path, issue_number=282, status="INIT")
    original_manifest = manifest_path.read_text()
    manager = IssueManager(target_dir=tmp_path)

    manager._update_manifest_status(282, "PLANNED")

    # Store is authoritative and updated.
    assert _store_status(tmp_path, 282) == "PLANNED"
    # The manifest mirror is NOT written (slice F contract).
    assert manifest_path.read_text() == original_manifest


def test_r001_unit_001_update_manifest_status_is_noop_for_unknown_issue(tmp_path):
    """R001: calling the helper for an issue number not in the manifest must not crash
    and must leave the manifest unchanged.
    """
    from atdd.coach.commands.issue import IssueManager

    manifest_path = _write_manifest(tmp_path, issue_number=282, status="INIT")
    original = manifest_path.read_text()
    manager = IssueManager(target_dir=tmp_path)

    manager._update_manifest_status(9999, "PLANNED")

    assert manifest_path.read_text() == original


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
