# URN: test:govern-lifecycle:govern-lifecycle:M004-SMOKE-001-the-real-store-drift-is-reported-and-survives-clearing
# Acceptance: acc:govern-lifecycle:M004-SMOKE-001-the-real-store-drift-is-reported-and-survives-clearing
# WMBT: wmbt:govern-lifecycle:M004
# Phase: SMOKE
# Layer: application
"""M004-SMOKE-001 — against this repository's own store, not a fixture.

The 104 stale bindings are real records produced by real maintenance. A fixture
would only prove the survey finds records built to be found; it could not show
that the survey's idea of "gone" matches the filesystem's.

Read-only. The survey must be safe to run before anyone decides to act on it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.worktree_bindings import stale_bindings
from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo


def _work_items(control_root: Path):
    from atdd.state.work_item_reader import WorkItemReader

    with WorkItemReader(control_root=control_root) as reader:
        return reader.all_work_items()


@pytest.mark.coder
@pytest.mark.platform
def test_every_reported_binding_names_a_genuinely_absent_directory():
    if not is_atdd_source_repo():
        pytest.skip("reads this repository's own State Store")

    control_root = Path(find_repo_root()).parent
    items = _work_items(control_root)
    assert items, "the store returned no work items — the survey would be vacuous"

    reported = list(stale_bindings(items))

    for binding in reported:
        assert not Path(binding.path).exists(), (
            f"{binding.slug} was reported stale but {binding.path} exists — the "
            "survey's notion of absent disagrees with the filesystem"
        )


@pytest.mark.coder
@pytest.mark.platform
def test_no_live_worktree_is_ever_proposed_for_clearing():
    """The direction that would do damage: never report a real fleet."""
    if not is_atdd_source_repo():
        pytest.skip("reads this repository's own State Store")

    control_root = Path(find_repo_root()).parent
    items = _work_items(control_root)
    reported = {b.slug for b in stale_bindings(items)}

    live = [
        i for i in items
        if i.get("worktree_path") and Path(str(i["worktree_path"])).exists()
    ]
    assert live, "no live bindings at all — this check would prove nothing"

    for item in live:
        assert str(item.get("slug")) not in reported, (
            f"{item.get('slug')} has a directory on disk and was proposed for "
            "clearing; that would unbind real work"
        )
