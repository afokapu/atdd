# URN: test:drive-state-machine:consolidate-store-writes:E003-SMOKE-001-live-consolidation-yields-single-store
# Acceptance: acc:drive-state-machine:E003-SMOKE-001-live-consolidation-yields-single-store
# WMBT: wmbt:drive-state-machine:E003
# Phase: SMOKE
# Runtime: python
# Layer: integration
# Assertion: behavioral
# Purpose: Against a real multi-worktree git project, consolidation collapses the divergent per-worktree stores into one control-root store that doctor/layout --check reports as the single store.
"""SMOKE Test for test:drive-state-machine:consolidate-store-writes:E003-SMOKE-001.

wagon: drive-state-machine | feature: consolidate-store-writes | phase: SMOKE
WMBT: wmbt:drive-state-machine:E003
Purpose: exercise the real resolver + real sqlite + real `atdd state` CLI over a
genuine flat-sibling git worktree layout — no stubs, no skips.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from atdd.state import cli as state_cli
from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore

WORK_ITEM = "work_item"
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git required for the live worktree smoke")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def _seed_store(db: Path, uid: str, state: str, issue: str) -> None:
    store = StateStore(connect(init_state_store(db_path=db)))
    store.objects.upsert(uid, WORK_ITEM, state=state)
    store.external_refs.link(uid, "github", "issue", issue)


def test_live_consolidation_yields_single_store(tmp_path):
    project = tmp_path / "project"
    main = project / "main"
    main.mkdir(parents=True)
    _git(main, "init", "-q")
    _git(main, "config", "user.email", "t@t.t")
    _git(main, "config", "user.name", "t")
    (main / "f.txt").write_text("x\n")
    _git(main, "add", "-A")
    _git(main, "commit", "-qm", "init")
    # a real linked worktree sibling of main/
    wt1 = project / "wt1"
    _git(main, "worktree", "add", "-q", str(wt1), "-b", "wt1")

    # divergent per-worktree stores: same issue 1346 at different phases
    _seed_store(main / ".atdd" / "state" / "state.sqlite", "wi-main", "INIT", "1346")
    _seed_store(wt1 / ".atdd" / "state" / "state.sqlite", "wi-wt1", "SMOKE", "1346")

    # BEFORE: layout is invalid (rogue per-worktree stores below the control root)
    assert state_cli.run(["layout", "--check", "--root", str(wt1)]) != 0

    rc = state_cli.run(["migrate-layout", "--project-root", str(project)])
    assert rc == 0

    shared = project / ".atdd" / "state" / "state.sqlite"
    assert shared.is_file()
    assert not (main / ".atdd" / "state" / "state.sqlite").exists()
    assert not (wt1 / ".atdd" / "state" / "state.sqlite").exists()

    # AFTER: exactly one store, single deduped row for issue 1346
    assert state_cli.run(["layout", "--check", "--root", str(wt1)]) == 0
    check = StateStore(connect(shared))
    linked = [
        o for o in check.objects.list(kind=WORK_ITEM)
        if any(r.ref_value == "1346" for r in check.external_refs.for_object(o.uid))
    ]
    assert len(linked) == 1
