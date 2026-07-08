# URN: test:drive-state-machine:consolidate-worktree-command:E008-SMOKE-001-create-makes-zero-commits-on-main
# Acceptance: acc:drive-state-machine:E008-SMOKE-001-create-makes-zero-commits-on-main
# WMBT: wmbt:drive-state-machine:E008
# Phase: SMOKE
# Harness: smoke
# Layer: integration
"""E008-SMOKE-001 — a real `atdd worktree create` produces zero new commits on main.

Issue #1347. End-to-end over a real worktree-ready layout (a ``main/`` checkout +
a local bare ``origin`` + a store-registered issue): run the create path and
assert local ``main``'s commit count is unchanged (the historical
``register issue #N in manifest`` on-main commit is gone) and a real worktree was
materialized based on ``origin/main``. Skips honestly when ``gh`` is absent (the
create path shells ``gh`` for the deferred draft PR); the assertion is the git
commit-count invariant, never faked.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.branch import BranchManager
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore

pytestmark = [pytest.mark.platform]


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


def _worktree_ready_repo(tmp_path: Path):
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-b", "main")
    _git(main, "config", "user.email", "t@example.com")
    _git(main, "config", "user.name", "Tester")
    (main / ".atdd").mkdir()
    (main / ".atdd" / "config.yaml").write_text("version: '1.0'\n")  # control-root marker
    (main / "README.md").write_text("seed\n")
    _git(main, "add", "-A")
    _git(main, "commit", "-m", "A")
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    _git(main, "remote", "add", "origin", str(bare))
    _git(main, "push", "origin", "main")
    _git(main, "remote", "set-head", "origin", "main")
    # register the issue in the store so create resolves it store-first (no GitHub)
    conn = connect(init_state_store(start=main))
    try:
        store = StateStore(conn)
        store.objects.upsert("do-a-thing", WORK_ITEM_KIND, state="RED", data={"issue_number": 4242, "type": "refactor"})
        store.external_refs.link("do-a-thing", GITHUB_PROVIDER, "issue", "4242")
        conn.commit()
    finally:
        conn.close()
    return main


def test_e008_smoke_001_create_makes_zero_commits_on_main(tmp_path):
    if shutil.which("gh") is None:
        pytest.skip("gh CLI unavailable — the create path's deferred-draft-PR step needs it")
    main = _worktree_ready_repo(tmp_path)
    commits_before = _git(main, "rev-list", "--count", "main").stdout.strip()

    rc = BranchManager(main).branch(4242)
    assert rc == 0

    commits_after = _git(main, "rev-list", "--count", "main").stdout.strip()
    assert commits_after == commits_before, "worktree create must make zero commits on local main"

    worktree = tmp_path / "refactor-do-a-thing"
    assert worktree.exists(), "the worktree directory was materialized"
    # the new branch is based on origin/main (its base commit is main's HEAD)
    base = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    assert base == _git(main, "rev-parse", "origin/main").stdout.strip()
