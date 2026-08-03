# URN: test:govern-lifecycle:issue-author-validate-locally-publish-once:Y007-SMOKE-001-real-cli-revise-writes-the-title
# Acceptance: acc:govern-lifecycle:Y007-SMOKE-001-real-cli-revise-writes-the-title
# WMBT: wmbt:govern-lifecycle:Y007
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: Against the real CLI in a real checkout with a real State Store, `--revise --title` changes the stored title and issues the GitHub title edit.
"""
RED Test for test:govern-lifecycle:issue-author-validate-locally-publish-once:Y007-SMOKE-001-real-cli-revise-writes-the-title
wagon: govern-lifecycle | feature: issue-author-validate-locally-publish-once | phase: RED
WMBT: wmbt:govern-lifecycle:Y007

Purpose: prove the SHIPPED entry point writes the title, not merely the seam.

An in-process unit proves the chain threads the argument; it does not prove the
command an operator runs does. That distinction is the whole defect — `--title`
looked functional because the command exited 0 and, when a body accompanied it,
the body's H1 changed. The measurement that caught it read the store and the
GitHub calls, not the exit code.

Real: a real `python -m atdd` subprocess, a real on-disk SQLite State Store, a
real `plan/` tree, and a real `gh` on PATH that records its arguments so the
projection resolves without touching production GitHub.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ._bind_issue_feature_helpers import (
    control_root,
    open_store,
    read_issue_data,
    seed_issue,
    write_plan_tree,
)

pytestmark = [pytest.mark.platform]

_ISSUE = 94073
_STALE = "smoke-title-probe"
_FRESH = "the title the operator actually asked for"
_REPO_SRC = Path(__file__).resolve().parents[4]  # .../src


def _recording_gh(root: Path) -> Path:
    """A real `gh` on PATH that appends every invocation to a JSONL log.

    Recording rather than omitting `gh` is deliberate: an absent binary makes
    every projection fail identically, so it cannot distinguish "issued a title
    edit that failed" from "never issued one". The defect under test is the
    second, so the stub has to succeed and be observable.
    """
    bindir = root / "stub-bin"
    bindir.mkdir(parents=True, exist_ok=True)
    log = root / "gh-calls.jsonl"
    script = bindir / "gh"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys, pathlib\n"
        f"pathlib.Path({str(log)!r}).open('a').write(json.dumps(sys.argv[1:]) + chr(10))\n"
        "print('{}')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return log


def _run_cli(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Invoke the real CLI in a separate process against ``root``."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO_SRC)
    env["ATDD_CONTROL_ROOT"] = str(root)
    env["PATH"] = f"{root / 'stub-bin'}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(
        [sys.executable, "-m", "atdd", "author", "issue", "--revise", *args],
        cwd=root, env=env, capture_output=True, text=True, timeout=120,
    )


def _gh_calls(log: Path) -> list[list[str]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


@pytest.fixture()
def repo(tmp_path):
    root = control_root(tmp_path)
    write_plan_tree(root)
    store = open_store(root)
    seed_issue(store, slug=_STALE, issue_number=_ISSUE, feature=None,
               body=f"# {_STALE}\n")
    store.conn.commit()
    log = _recording_gh(root)
    return root, store, log


def test_real_cli_revise_writes_the_title_to_the_store(repo) -> None:
    """The shipped artifact writes the field, not merely the body."""
    root, store, _log = repo

    result = _run_cli(root, str(_ISSUE), "--title", _FRESH)

    assert result.returncode == 0, (
        f"real CLI `--revise --title` exited {result.returncode}\n"
        f"stderr:\n{result.stderr}"
    )
    assert read_issue_data(store, _ISSUE).get("title") == _FRESH, (
        "the real CLI exited 0 and left the stored title unchanged — the "
        "behaviour measured on 2026-08-02, and the reason #1636's issue title "
        "and body H1 disagreed until an operator ran `gh issue edit` by hand"
    )


def test_real_cli_revise_issues_the_github_title_edit(repo) -> None:
    """The live issue title must move, or it diverges from the body H1."""
    root, _store, log = repo

    _run_cli(root, str(_ISSUE), "--title", _FRESH)

    calls = _gh_calls(log)
    carrying = [c for c in calls if _FRESH in c]
    assert carrying, (
        "the real CLI issued no `gh` call carrying the new title. Recorded "
        f"calls: {calls!r}. The stored title and the live issue title now "
        "disagree, which is exactly the divergence this WMBT closes"
    )
    assert any(str(_ISSUE) in c for c in carrying), (
        f"a title edit was issued but not for issue #{_ISSUE}: {carrying!r}"
    )


def test_real_cli_refuses_an_unhonoured_flag_without_touching_github(repo) -> None:
    """A refused revision exits non-zero and performs no projection at all."""
    root, store, log = repo

    result = _run_cli(root, str(_ISSUE), "--type", "bug", "--branch", "feat/nope")

    assert result.returncode != 0, (
        "the real CLI exited 0 for `--revise --branch`, a flag the revise path "
        f"reads nothing from\nstdout:\n{result.stdout[:400]}"
    )
    assert "--branch" in result.stderr, (
        f"the refusal did not name --branch; stderr was:\n{result.stderr}"
    )
    assert not _gh_calls(log), (
        f"a refused revision still called gh: {_gh_calls(log)!r}"
    )
    assert read_issue_data(store, _ISSUE).get("body") == f"# {_STALE}\n", (
        "a refused revision still mutated the stored body"
    )
