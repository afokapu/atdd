# URN: test:govern-lifecycle:close-substrate-friction-regressions:E072-SMOKE-001-real-push-carries-the-resync-or-is-refused
# Acceptance: acc:govern-lifecycle:E072-SMOKE-001-real-push-carries-the-resync-or-is-refused
# WMBT: wmbt:govern-lifecycle:E072
# Phase: SMOKE
# Layer: integration
"""E072-SMOKE-001 — through real git against a real remote (#1888).

The UNIT tests execute the hook BLOCKS. This one installs them as real hooks and
runs `git commit` and `git push` for real, because the defect is defined by git's
own plumbing: git resolves the refs it will send before invoking pre-push, so a
staged file cannot reach the remote. No amount of block-level testing can observe
that — only an actual push against an actual remote can.

The assertion that matters is on the REMOTE's content, not on the hook's output.
The shipped hook printed a success notice and exited 0; every claim it made was
true of the worktree and false of the remote.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ._e072_registry_harness import extract_block, make_repo

pytestmark = [pytest.mark.platform]


def _git(repo: Path, *args: str, env=None, check: bool = True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, env=env, check=check,
    )


def _remote_file(remote: Path, path: str) -> str:
    return subprocess.run(
        ["git", "--git-dir", str(remote), "show", f"main:{path}"],
        capture_output=True, text=True, check=True,
    ).stdout


def _install(repo: Path, name: str, body: str) -> None:
    hook = repo / ".git" / "hooks" / name
    hook.write_text("#!/usr/bin/env bash\n" + body + "\n", encoding="utf-8")
    hook.chmod(0o755)


@pytest.fixture()
def wired(tmp_path):
    """A repo with the shipped registry blocks installed as real git hooks, and a
    bare remote to push at."""
    repo, env = make_repo(tmp_path)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "origin", "main", env=env)

    _install(repo, "pre-commit", extract_block("pre-commit", "# --- Registry mirror auto-heal"))
    _install(repo, "pre-push", extract_block("pre-push", "# --- Registry mirror drift gate"))
    return repo, remote, env


def test_a_real_push_carries_the_resync_to_the_remote(wired) -> None:
    repo, remote, env = wired
    (repo / ".drift").touch()
    (repo / "source.yaml").write_text("v2\n", encoding="utf-8")
    _git(repo, "add", "source.yaml")

    _git(repo, "commit", "-qm", "change source", env=env)
    push = _git(repo, "push", "origin", "main", env=env, check=False)

    assert push.returncode == 0, push.stderr
    assert _remote_file(remote, "plan/_wagons.yaml").strip() == "total: 12", (
        "the remote carries the DRIFTED mirror — the resync never left the worktree"
    )
    local = _git(repo, "rev-parse", "HEAD").stdout.strip()
    pushed = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "main"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert local == pushed, "local HEAD and the remote diverged behind an exit-0 push"
    assert _git(repo, "status", "--porcelain").stdout.strip() == "", (
        "the resync was left uncommitted in the worktree"
    )


def test_drift_surviving_to_push_time_is_refused_and_ships_nothing(wired) -> None:
    """--no-verify skips pre-commit, so drift reaches the push. The gate must refuse
    and the remote must not move."""
    repo, remote, env = wired
    before = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "main"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    (repo / ".drift").touch()
    (repo / "source.yaml").write_text("v3\n", encoding="utf-8")
    _git(repo, "add", "source.yaml")
    _git(repo, "commit", "-qm", "drifted commit", "--no-verify", env=env)

    push = _git(repo, "push", "origin", "main", env=env, check=False)

    assert push.returncode != 0, "a drifted push was allowed through"
    after = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "main"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert before == after, "the remote moved despite a refused push"
