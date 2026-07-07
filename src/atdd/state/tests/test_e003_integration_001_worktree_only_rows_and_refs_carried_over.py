# URN: test:drive-state-machine:consolidate-store-writes:E003-INTEGRATION-001-worktree-only-rows-and-refs-carried-over
# Acceptance: acc:drive-state-machine:E003-INTEGRATION-001-non-duplicate-rows-and-refs-carried-over-without-loss
# WMBT: wmbt:drive-state-machine:E003
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: Objects, external_refs, and events that exist only in a worktree store are carried into the target without loss when they are not duplicates.
"""RED Test for test:drive-state-machine:consolidate-store-writes:E003-INTEGRATION-001.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: RED
WMBT: wmbt:drive-state-machine:E003
Purpose: a worktree-only work_item (present in NO other store) is merged into the
target with its external_ref and events intact — no count regression, no loss.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state.cli import migrate_layout
from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore

WORK_ITEM = "work_item"


def _store_at(db_path: Path) -> StateStore:
    return StateStore(connect(init_state_store(db_path=db_path)))


def test_worktree_only_rows_and_refs_carried_over(tmp_path):
    project = tmp_path / "project"
    project.mkdir()

    target = _store_at(project / ".atdd" / "state" / "state.sqlite")
    for issue in ("1310", "1314"):
        uid = f"wi-{issue}"
        target.objects.upsert(uid, WORK_ITEM, state="COMPLETE")
        target.external_refs.link(uid, "github", "issue", issue)

    # worktree store with an issue (1399) present nowhere else, plus an event
    wt = project / "wt1"
    (wt / ".git").mkdir(parents=True)
    src = _store_at(wt / ".atdd" / "state" / "state.sqlite")
    src.objects.upsert("wi-1399", WORK_ITEM, state="GREEN")
    src.external_refs.link("wi-1399", "github", "issue", "1399")
    src.events.append("phase_changed", object_uid="wi-1399", payload={"to": "GREEN"})

    migrate_layout(project_root=project)

    check = StateStore(connect(project / ".atdd" / "state" / "state.sqlite"))
    issues = {
        r.ref_value
        for o in check.objects.list(kind=WORK_ITEM)
        for r in check.external_refs.for_object(o.uid)
    }
    # union of distinct issues across all input stores — nothing dropped
    assert {"1310", "1314", "1399"} <= issues
    # 1399's external_ref and event carried over
    ref = check.external_refs.resolve("github", "issue", "1399")
    assert ref is not None
    assert check.events.list(object_uid=ref.object_uid)
