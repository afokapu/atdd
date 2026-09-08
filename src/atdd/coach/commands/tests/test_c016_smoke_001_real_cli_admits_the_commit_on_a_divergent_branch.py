# URN: test:govern-lifecycle:reliable-manifest-registration:C016-SMOKE-001-real-cli-admits-the-commit-on-a-divergent-branch
# Acceptance: acc:govern-lifecycle:C016-SMOKE-001-real-cli-admits-the-commit-on-a-divergent-branch
# WMBT: wmbt:govern-lifecycle:C016
# Phase: SMOKE
# Layer: smoke
# Assertion: behavioral
"""C016-SMOKE-001 — the real CLI the pre-commit hook calls admits the commit.

Issue #1720. The unit acceptances prove the resolution in-process. This one
proves the thing that actually blocks a worker: the hook runs
``atdd coach is-registered "$BRANCH"`` as a SEPARATE REAL PROCESS and blocks the
commit on a non-zero exit. So the exit code is asserted from a real subprocess
running the real CLI entry point — no in-process import of the module under
test, no monkeypatching, no fakes anywhere on the resolution path.

Mixed coverage, stated honestly: the CLI, the entry point, the store and the
resolution are all real; the Control Root is a synthetic ``tmp_path`` layout
with throwaway uids, so no live issue, no live Control Root and no GitHub I/O is
touched. The subprocess is pointed at this checkout's ``src`` rather than the
installed toolkit, because the installed toolkit lags merged main (#1712) and
would otherwise answer from a build that does not contain the fix.

Both exit codes are asserted. Exit 0 alone would be satisfied by a gate that
stopped refusing anything at all, so the unregistered branch's exit 1 is what
makes the passing leg mean something. The third assertion pins that the answer
came from the store and not from a reinstated ``.atdd/manifest.yaml`` fallback —
#1400 CORE-034 retired that on the principle that two sources can disagree, and
this fix must stay one source with two indexes over it.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore

pytestmark = [pytest.mark.platform]

_UID = "resolve-approval-token-path-via-shared-control-root"
_REGISTERED_BRANCH = "feat/resolve-approval-token-control-root"
_UNREGISTERED_BRANCH = "feat/never-registered-anywhere"

_REPO_SRC = Path(__file__).resolve().parents[4]


def _seeded_control_root(tmp_path: Path) -> Path:
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    conn = connect(init_state_store(start=tmp_path))
    try:
        store = StateStore(conn)
        store.objects.upsert(
            _UID, WORK_ITEM_KIND, state="RED", data={"issue_number": 1376, "branch": _REGISTERED_BRANCH}
        )
        store.external_refs.link(_UID, GITHUB_PROVIDER, "issue", "1376")
        store.objects.upsert(
            "an-unrelated-completed-item", WORK_ITEM_KIND, state="COMPLETE", data={"issue_number": 1377}
        )
        conn.commit()
    finally:
        conn.close()
    return tmp_path


def _run_is_registered(root: Path, branch: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO_SRC)
    env.pop("CI", None)
    return subprocess.run(
        [sys.executable, "-m", "atdd.cli", "coach", "is-registered", branch],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=120,
    )


def test_c016_smoke_001_real_cli_admits_the_commit_on_a_divergent_branch(tmp_path):
    root = _seeded_control_root(tmp_path)

    registered = _run_is_registered(root, _REGISTERED_BRANCH)
    assert registered.returncode == 0, (
        "the real CLI must exit 0 for a registered branch whose name is not its "
        f"work item's uid, so the pre-commit hook admits the commit; got "
        f"{registered.returncode}\nstdout: {registered.stdout}\nstderr: {registered.stderr}"
    )

    unregistered = _run_is_registered(root, _UNREGISTERED_BRANCH)
    assert unregistered.returncode == 1, (
        "the real CLI must still exit 1 for a branch bound to no work item, so "
        f"the hook still blocks it; got {unregistered.returncode}\n"
        f"stdout: {unregistered.stdout}\nstderr: {unregistered.stderr}"
    )

    # The retired fallback is not reinstated: the seeded Control Root has no
    # .atdd/manifest.yaml, and neither invocation created or required one.
    assert not (root / ".atdd" / "manifest.yaml").exists(), (
        "the answer must come from the State Store alone — a manifest appearing "
        "here would mean the #1400 CORE-034 fallback was reinstated"
    )
