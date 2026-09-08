# URN: test:reconcile-local-store:reconcile-store-state:R002-UNIT-001-conflict-report-names-events-and-backup
# Acceptance: acc:reconcile-local-store:R002-UNIT-001-conflict-report-names-events-and-backup
# WMBT: wmbt:reconcile-local-store:R002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: an invalid replay produces an actionable conflict report — each offending event with its object uid and kind, the incoming projection state for those objects, the retained backup path — and the command exits non-zero. Refs #1400.
"""The conflict report is actionable, not merely truthful (R002-UNIT-001).

wagon: reconcile-local-store | feature: reconcile-store-state | phase: RED
WMBT: wmbt:reconcile-local-store:R002

A conflict is where the machine stops and the human starts, so the report has to carry
everything the human needs to decide: *which* of their events was refused, *what* the
shared truth says about that object now, and *where* the undo lives. A report that
says only "conflict" hands the developer a store they are now afraid to touch. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state import authoring
from atdd.state.reconcile import ReplayConflictError, hydrate_store, reconcile
from atdd.state.reconcile_cli import dispatch

from ._helpers import UID_A, checkout, commit_all, document, store, write_projection


class _Args:
    """The parsed-args shape ``atdd state reconcile`` dispatches on."""

    def __init__(self, root) -> None:
        self.op = "reconcile"
        self.root = str(root)
        self.head = None
        self.check_dirty = False
        self.allow_deletions = None  # no mass-retirement assertion (#1580)


def test_r002_unit_001_conflict_report_names_events_and_backup(tmp_path, capsys) -> None:
    """The report names the offending event, the incoming state, and the backup path."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A, phase="PLANNED", owner="dev-a")])
    commit_all(repo, "base projection")
    hydrate_store(repo)

    # B authors a transition from PLANNED. A merges a different one first.
    conn = store(repo)
    try:
        transition = authoring.request_transition(conn, UID_A, "GREEN")
    finally:
        conn.close()

    write_projection(repo, [document(UID_A, phase="SMOKE", owner="dev-a")])
    head = commit_all(repo, "A merged a different transition")

    with pytest.raises(ReplayConflictError) as raised:
        reconcile(repo)
    report = raised.value.report
    rendered = report.render()

    # The report lists each offending overlay event with its object uid and event kind.
    assert len(report.conflicts) == 1
    conflict = report.conflicts[0]
    assert conflict.event.event_id == transition.event_id
    assert conflict.event.object_uid == UID_A
    assert conflict.event.kind == "phase_transition_requested"
    assert transition.event_id in rendered
    assert UID_A in rendered
    assert "phase_transition_requested" in rendered

    # The report shows the incoming projection state for those objects.
    assert conflict.incoming is not None
    assert conflict.incoming["phase"] == "SMOKE"
    assert "'SMOKE'" in rendered
    assert "divergence" in rendered  # it says WHY, not just that

    # The report names the retained sqlite backup path.
    assert report.backup_path is not None
    assert report.backup_path.exists()
    assert str(report.backup_path) in rendered

    # And it tells the operator the anchor did not move.
    assert report.head == head
    assert report.base_commit[:12] in rendered

    # The command exits non-zero, printing the report rather than a traceback.
    assert dispatch(_Args(repo)) == 1
    printed = capsys.readouterr().out
    assert "CONFLICT" in printed
    assert str(report.backup_path.parent) in printed
