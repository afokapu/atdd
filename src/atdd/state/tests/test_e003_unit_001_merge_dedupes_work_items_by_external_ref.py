# URN: test:drive-state-machine:consolidate-store-writes:E003-UNIT-001-merge-dedupes-work-items-by-external-ref
# Acceptance: acc:drive-state-machine:E003-UNIT-001-merge-dedupes-work-items-by-external-ref
# WMBT: wmbt:drive-state-machine:E003
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: Consolidating stores that hold the same GitHub issue yields ONE work_item keyed by external_refs, with the most-advanced state preserved.
"""RED Test for test:drive-state-machine:consolidate-store-writes:E003-UNIT-001.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: RED
WMBT: wmbt:drive-state-machine:E003
Purpose: the consolidation merge de-duplicates work_items on their external_refs
GitHub-issue link (the GitHub-linked row wins; the most-advanced state is kept),
and an orphan row with no external_ref is never silently dropped.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state.cli import migrate_layout
from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore

WORK_ITEM = "work_item"


def _store_at(db_path: Path) -> StateStore:
    return StateStore(connect(init_state_store(db_path=db_path)))


def _mk_child(project: Path, name: str) -> Path:
    child = project / name
    (child / ".git").mkdir(parents=True, exist_ok=True)
    (child / ".atdd" / "state").mkdir(parents=True, exist_ok=True)
    return child


def test_merge_dedupes_work_items_by_external_ref(tmp_path):
    project = tmp_path / "project"
    project.mkdir()

    # target: control-root store holds issue 1346 (INIT), GitHub-linked
    target = _store_at(project / ".atdd" / "state" / "state.sqlite")
    target.objects.upsert("wi-1346-main", WORK_ITEM, state="INIT")
    target.external_refs.link("wi-1346-main", "github", "issue", "1346")

    # source wt1: same issue 1346 but more advanced (SMOKE), different local uid
    wt1 = _mk_child(project, "wt1")
    s1 = _store_at(wt1 / ".atdd" / "state" / "state.sqlite")
    s1.objects.upsert("wi-1346-wt1", WORK_ITEM, state="SMOKE")
    s1.external_refs.link("wi-1346-wt1", "github", "issue", "1346")

    # source wt2: an orphan work_item with NO external_ref
    wt2 = _mk_child(project, "wt2")
    s2 = _store_at(wt2 / ".atdd" / "state" / "state.sqlite")
    s2.objects.upsert("wi-orphan", WORK_ITEM, state="GREEN")

    result = migrate_layout(project_root=project)

    shared = project / ".atdd" / "state" / "state.sqlite"
    assert result.store_path == shared

    check = StateStore(connect(shared))
    # exactly one work_item resolvable via the shared GitHub link
    ref = check.external_refs.resolve("github", "issue", "1346")
    assert ref is not None
    linked = check.objects.get(ref.object_uid)
    assert linked is not None
    # dedup collapsed the INIT + SMOKE pair to a single row at the most-advanced state
    github_1346 = [
        o for o in check.objects.list(kind=WORK_ITEM)
        if check.external_refs.for_object(o.uid)
        and any(r.ref_value == "1346" for r in check.external_refs.for_object(o.uid))
    ]
    assert len(github_1346) == 1
    assert github_1346[0].state == "SMOKE"
    # the orphan row is retained, never silently dropped
    assert check.objects.get("wi-orphan") is not None
    # the result reports the collapse
    assert result.deduped == 1
