# URN: test:govern-lifecycle:hooks-must-not-drift-from-template:E063-SMOKE-001-real-commit-runs-changed-packaged-hook
# Acceptance: acc:govern-lifecycle:E063-SMOKE-001-real-commit-runs-changed-packaged-hook
# WMBT: wmbt:govern-lifecycle:E063
# Phase: SMOKE
# Layer: backend.integration
"""AC-SMOKE-001: a real `git commit` runs the CHANGED packaged hook (#1492).

The unit/integration cover drives the dispatcher directly. This drives the path
that actually matters: git invoking the hook through `core.hooksPath`, with no
refresh command run between the packaged hook changing and the commit.

That distinction is the whole issue. `.atdd/hooks/*` was a snapshot copy, so a
hook fix reached only repos initialised after it landed — and every test that
called a hook directly still passed, because the template it called was fine.
Only running git proves the fix reaches the operator.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.initializer import ProjectInitializer

pytestmark = [pytest.mark.coach, pytest.mark.slow]


def _git(repo: Path, *args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL, **kw
    )


def _fake_atdd_bin(bin_dir: Path, packaged_hooks: Path) -> None:
    """An `atdd` implementing just `hooks path <name>` — the dispatcher's seam."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "atdd"
    shim.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "hooks" ] && [ "$2" = "path" ]; then\n'
        f'    p="{packaged_hooks}/$3"\n'
        '    [ -f "$p" ] || exit 1\n'
        '    printf "%s\\n" "$p"\n'
        "    exit 0\n"
        "fi\n"
        "exit 1\n"
    )
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def test_real_commit_runs_the_changed_packaged_hook(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "feat/x", str(repo)], check=True, capture_output=True)
    _git(repo, "config", "user.email", "t@t.test")
    _git(repo, "config", "user.name", "Tester")
    (repo / "README.md").write_text("seed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore: seed", "--no-verify")

    # A packaged hook that allows, and the dispatcher installed against it.
    packaged = tmp_path / "packaged"
    packaged.mkdir()
    (packaged / "commit-msg").write_text("#!/bin/sh\nexit 0\n")
    bin_dir = tmp_path / "bin"
    _fake_atdd_bin(bin_dir, packaged)

    hooks_dir = repo / ".atdd" / "hooks"
    hooks_dir.mkdir(parents=True)
    body = ProjectInitializer(repo)._dispatcher_body("commit-msg")
    assert body is not None
    dispatcher = hooks_dir / "commit-msg"
    dispatcher.write_text(body)
    dispatcher.chmod(dispatcher.stat().st_mode | stat.S_IEXEC)
    _git(repo, "config", "core.hooksPath", str(hooks_dir))

    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ.get('PATH', '')}")

    # Control: the commit succeeds against the unchanged packaged hook. Without
    # this, a later block could just mean the dispatcher is broken.
    (repo / "README.md").write_text("seed\nchange one\n")
    _git(repo, "add", "-A")
    ok = _git(repo, "commit", "-m", "chore: baseline commit", env=env)
    assert ok.returncode == 0, f"dispatcher blocked a good commit: {ok.stderr}"
    commits_before = _git(repo, "log", "--oneline").stdout.strip().splitlines()
    assert len(commits_before) == 2

    # A hook fix lands in the package. NOTHING is refreshed.
    (packaged / "commit-msg").write_text(
        '#!/bin/sh\necho "E063-SMOKE-CANARY: new packaged logic executed" >&2\nexit 1\n'
    )

    (repo / "README.md").write_text("seed\nchange one\nchange two\n")
    _git(repo, "add", "-A")
    blocked = _git(repo, "commit", "-m", "chore: should be blocked", env=env)

    assert blocked.returncode != 0, (
        "git ACCEPTED the commit — the changed packaged hook never ran, so a "
        "hook fix would reach nobody (#1492)"
    )
    assert "E063-SMOKE-CANARY" in (blocked.stderr + blocked.stdout), (
        f"the new packaged logic did not execute: {blocked.stderr!r}"
    )
    commits_after = _git(repo, "log", "--oneline").stdout.strip().splitlines()
    assert commits_after == commits_before, "a commit object was created despite the block"
