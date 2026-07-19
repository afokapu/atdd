# URN: test:drive-state-machine:record-agent-session-identity:E010-SMOKE-001-survives-no-verify-and-never-blocks-the-commit
# Acceptance: acc:drive-state-machine:E010-SMOKE-001-survives-no-verify-and-never-blocks-the-commit
# WMBT: wmbt:drive-state-machine:E010
# Phase: SMOKE
# Harness: smoke
# Layer: integration
"""E010-SMOKE-001 — capture survives `--no-verify`, and never blocks a commit.

Issue #1540, Decision 2 — the entire reason the hook is post-commit rather than
pre-commit, asserted against real git rather than trusted from the decision:

* `--no-verify` skips pre-commit and commit-msg. It does NOT skip post-commit.
  Agents use `--no-verify` routinely, so a pre-commit capture would silently
  miss exactly the commits it most needs.
* post-commit runs after the commit object exists, so a failing store write
  cannot cost the operator their commit. Injected here, not argued.

Real git, real hook file, real subprocess: an in-process call would prove
nothing about what git actually runs.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from atdd.state.agent_session import REF_KIND_SESSION

from ._agent_session_helpers import SLUG, control_root, open_store, seed_work_item

pytestmark = [pytest.mark.platform]

BRANCH = "feat/record-agent-session-identity-at-write-points"
SESSION_ID = "6453e644-64cd-4254-add5-fa30135b52b1"

# The #1492 fixed-content dispatcher: the hook only execs the packaged logic.
HOOK = """#!/bin/sh
exec {python} -c 'import sys; from atdd.state.agent_session import capture_post_commit; \
capture_post_commit()' "$@"
"""

# The same dispatcher, pointed at a capture that raises — to prove a broken
# store cannot cost a commit.
EXPLODING_HOOK = """#!/bin/sh
exec {python} -c 'raise SystemExit(1)' "$@"
"""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)


def _repo(tmp_path: Path, hook_body: str) -> Path:
    repo = tmp_path / "wt"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", BRANCH)
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    hook = repo / ".git" / "hooks" / "post-commit"
    hook.write_text(hook_body.format(python=sys.executable))
    hook.chmod(0o755)
    return repo


def _commit(repo: Path, name: str, env: dict) -> subprocess.CompletedProcess:
    (repo / name).write_text("x")
    _git(repo, "add", name)
    return subprocess.run(
        ["git", "-C", str(repo), "commit", "--no-verify", "-m", f"add {name}"],
        capture_output=True, text=True, env=env,
    )


def test_e010_smoke_001_capture_survives_no_verify(tmp_path, monkeypatch):
    root = control_root(tmp_path)
    store = open_store(root)
    seed_work_item(store, data={"issue_number": 1540, "branch": BRANCH})
    store.conn.commit()

    repo = _repo(tmp_path, HOOK)
    import os
    env = {**os.environ,
           "ATDD_CONTROL_ROOT": str(root),
           "CLAUDE_CODE_SESSION_ID": SESSION_ID}

    proc = _commit(repo, "a.txt", env)
    assert proc.returncode == 0, proc.stderr

    store = open_store(root)
    refs = [r for r in store.external_refs.all() if r.ref_kind == REF_KIND_SESSION]
    assert len(refs) == 1, (
        "--no-verify skips pre-commit but NOT post-commit; capture must still have run"
    )
    assert refs[0].ref_value == SESSION_ID


def test_e010_smoke_001_failing_capture_never_blocks_the_commit(tmp_path):
    import os

    repo = _repo(tmp_path, EXPLODING_HOOK)
    proc = _commit(repo, "b.txt", {**os.environ})

    assert proc.returncode == 0, (
        "post-commit runs after the commit exists; a failing hook must not fail it"
    )
    log = _git(repo, "log", "--oneline")
    assert "add b.txt" in log.stdout, "the commit object must exist despite the hook failing"
