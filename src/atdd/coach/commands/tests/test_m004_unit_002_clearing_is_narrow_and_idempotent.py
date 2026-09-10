# URN: test:govern-lifecycle:govern-lifecycle:M004-UNIT-002-clearing-removes-only-the-false-value-and-reports-nothing-when-clean
# Acceptance: acc:govern-lifecycle:M004-UNIT-002-clearing-removes-only-the-false-value-and-reports-nothing-when-clean
# WMBT: wmbt:govern-lifecycle:M004
# Phase: RED
# Layer: application
"""M004-UNIT-002 — clearing touches the false value and nothing else.

Two properties, both easy to lose:

  NARROW — the record carries branch, train, phase and more alongside the
  binding. Rewriting the whole record to remove one field is how a repair
  silently reverts something a parallel session wrote.

  IDEMPOTENT — this is meant to be runnable on a schedule. A second pass over a
  clean store must say nothing, or the report becomes noise and stops being read.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.worktree_bindings import clear_binding, stale_bindings


@pytest.mark.coder
def test_clearing_leaves_every_other_field_intact(tmp_path):
    record = {
        "slug": "wi-7",
        "worktree_path": str(tmp_path / "gone"),
        "branch": "feat/keep-me",
        "train": "train:self-compliance:validate-lifecycle",
        "status": "REFACTOR",
    }

    cleared = clear_binding(record)

    assert not cleared.get("worktree_path"), "the false value must not survive"
    for field in ("branch", "train", "status"):
        assert cleared[field] == record[field], (
            f"{field} was rewritten; only the binding was in question"
        )


@pytest.mark.coder
def test_clearing_is_not_a_lifecycle_event(tmp_path):
    """Phase and state are untouched — retiring a path is not a transition."""
    record = {"slug": "wi-8", "worktree_path": str(tmp_path / "gone"), "status": "SMOKE"}

    assert clear_binding(record)["status"] == "SMOKE"


@pytest.mark.coder
def test_a_second_pass_reports_nothing(tmp_path):
    """Idempotent: a scheduled run stays quiet once the store is clean."""
    items = [{"slug": "wi-9", "worktree_path": str(tmp_path / "gone")}]

    first = list(stale_bindings(items))
    assert len(first) == 1

    items = [clear_binding(r) for r in items]

    assert list(stale_bindings(items)) == [], (
        "after clearing, the same survey must find nothing — otherwise a "
        "scheduled run reports the same drift forever and gets ignored"
    )
