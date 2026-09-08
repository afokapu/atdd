# URN: test:integration-hardening:run-upgrade-unattended:E009-SMOKE-001-a-real-post-merge-run-cannot-refuse-the-operation-it-follows
# Acceptance: acc:integration-hardening:E009-SMOKE-001-a-real-post-merge-run-cannot-refuse-the-operation-it-follows
# WMBT: wmbt:integration-hardening:E009
# Phase: SMOKE
# Layer: application
# Runtime: python
# Assertion: behavioral
"""E009-SMOKE-001 — "git ignores post-* exit codes" verified, not assumed.

SMOKE Test for acc:integration-hardening:E009-SMOKE-001-a-real-post-merge-run-cannot-refuse-the-operation-it-follows
wagon: integration-hardening | feature: run-upgrade-unattended | phase: SMOKE
WMBT: wmbt:integration-hardening:E009

Every safety argument in #1762 reduces to one claim about a tool this repo does
not own: that git discards the exit status of ``post-merge`` and
``post-checkout``. If that claim were wrong, moving the upgrade there would not
be safer than the pre-push gate — it would be worse, because the operation
would already have happened when the refusal arrived.

So it is checked against a real ``git``, in a real repository, with the packaged
hook templates installed and executed by a real ``/bin/sh``. Nothing about git's
hook dispatch is mocked. The self-upgrade is driven to its worst realistic
behaviour — noisy on both streams and exiting non-zero — because the question is
what git does *about* a failing post-hook, and a hook that succeeds cannot
answer it.

``core.hooksPath`` is deliberately never written: it is shared by every worktree
of a repository and an unscoped write to it caused #793. The hooks are installed
by copying them into the throwaway repo's own ``.git/hooks/``.
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

# `slow` keeps this out of the post-commit hook's blast-radius run (-m 'not slow');
# it is a real-git, real-subprocess test and belongs in CI, not after every commit.
pytestmark = [pytest.mark.coach, pytest.mark.platform, pytest.mark.smoke, pytest.mark.slow]

HOOKS_DIR = Path(__file__).resolve().parents[1]

#: How the stub behaves. "noisy-failure" is the shape that matters; "silent" is
#: the control, proving the assertions are not vacuously true of any hook.
_STUB_BEHAVIOURS = ["noisy-failure", "silent"]


def _git(repo: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True,
        env=env, check=False,
    )


def _install_stub_atdd(bin_dir: Path, behaviour: str) -> None:
    """Write a fake ``atdd`` onto PATH for the hook to find.

    The hook's contract is with the *command*, so the command is the honest
    injection point. Only ``self-upgrade`` is affected; ``state reconcile``
    succeeds, so this measures the self-upgrade and not the reconcile above it.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "atdd"
    if behaviour == "noisy-failure":
        body = (
            "  echo 'STUB stdout: self-upgrade wrote where it should not'\n"
            "  echo 'STUB stderr: self-upgrade failed hard' >&2\n"
            "  exit 3\n"
        )
    else:
        body = "  exit 0\n"
    script.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = 'self-upgrade' ]; then\n"
        f"{body}"
        "fi\n"
        "exit 0\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture()
def live_repo(tmp_path: Path) -> Path:
    """A real git repo with the packaged post-merge and post-checkout hooks."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "smoke@example.com")
    _git(repo, "config", "user.name", "Smoke")
    (repo / "base.txt").write_text("base\n")
    _git(repo, "add", "base.txt")
    _git(repo, "commit", "-qm", "base")

    for name in ("post-merge", "post-checkout"):
        installed = repo / ".git" / "hooks" / name
        installed.write_text((HOOKS_DIR / name).read_text(encoding="utf-8"))
        installed.chmod(installed.stat().st_mode | stat.S_IEXEC)

    (repo / "topic.txt").write_text("topic\n")
    _git(repo, "checkout", "-q", "-b", "topic")
    _git(repo, "add", "topic.txt")
    _git(repo, "commit", "-qm", "topic")
    _git(repo, "checkout", "-q", "main")
    return repo


def _hook_env(bin_dir: Path) -> dict:
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    # The hooks no-op under CI by design. This smoke must exercise the real path,
    # so the variable is cleared rather than inherited from whatever runs pytest.
    env.pop("CI", None)
    return env


@pytest.mark.parametrize("behaviour", _STUB_BEHAVIOURS)
def test_e009_smoke_001_a_real_merge_lands_whatever_the_hook_did(
    live_repo: Path, tmp_path: Path, behaviour: str,
):
    """`git merge` exits 0 and the merge lands, even when the hook exits 3."""
    bin_dir = tmp_path / f"bin-merge-{behaviour}"
    _install_stub_atdd(bin_dir, behaviour)
    env = _hook_env(bin_dir)

    hooks_path_before = _git(live_repo, "config", "--get", "core.hooksPath").stdout
    tracked_before = _git(live_repo, "ls-files").stdout

    merged = subprocess.run(
        ["git", "merge", "--no-ff", "-m", "merge topic", "topic"],
        cwd=str(live_repo), capture_output=True, text=True, env=env, check=False,
    )

    assert merged.returncode == 0, (
        "git honoured a post-merge hook's exit code — the premise of #1762 does not "
        f"hold on this git:\nstdout:\n{merged.stdout}\nstderr:\n{merged.stderr}"
    )
    assert (live_repo / "topic.txt").exists(), "the merge did not actually land"
    assert "STUB stdout" not in merged.stdout, (
        f"hook output reached the stdout git's callers parse:\n{merged.stdout}"
    )
    assert _git(live_repo, "config", "--get", "core.hooksPath").stdout == hooks_path_before, (
        "the hook wrote core.hooksPath — the shared key that caused #793"
    )
    assert _git(live_repo, "status", "--porcelain").stdout == "", (
        "the hook left an untracked or modified file behind"
    )
    assert _git(live_repo, "ls-files").stdout == tracked_before + "topic.txt\n", (
        "the hook changed the tracked file set"
    )


@pytest.mark.parametrize("behaviour", _STUB_BEHAVIOURS)
def test_e009_smoke_001_a_real_checkout_switches_whatever_the_hook_did(
    live_repo: Path, tmp_path: Path, behaviour: str,
):
    """`git checkout` exits 0 and the branch switches, even when the hook exits 3."""
    bin_dir = tmp_path / f"bin-checkout-{behaviour}"
    _install_stub_atdd(bin_dir, behaviour)
    env = _hook_env(bin_dir)

    hooks_path_before = _git(live_repo, "config", "--get", "core.hooksPath").stdout

    switched = subprocess.run(
        ["git", "checkout", "topic"],
        cwd=str(live_repo), capture_output=True, text=True, env=env, check=False,
    )

    assert switched.returncode == 0, (
        "git honoured a post-checkout hook's exit code:\n"
        f"stdout:\n{switched.stdout}\nstderr:\n{switched.stderr}"
    )
    head = _git(live_repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    assert head == "topic", f"the branch did not switch; HEAD is {head!r}"
    assert "STUB stdout" not in switched.stdout
    assert _git(live_repo, "config", "--get", "core.hooksPath").stdout == hooks_path_before
    assert _git(live_repo, "status", "--porcelain").stdout == ""


def test_e009_smoke_001_the_real_cli_verb_exits_zero_and_leaves_stdout_alone(tmp_path: Path):
    """The real `atdd self-upgrade`, as a subprocess, in a directory that is not a repo.

    No stub: this is the command the hooks actually call, run through the real
    CLI. It must exit 0 and print nothing to stdout whatever it decides — the
    output discipline the hooks depend on, measured at the process boundary
    rather than in-process where a patched stream could hide a mistake.
    """
    repo_root = Path(__file__).resolve().parents[6]
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{repo_root / 'src'}{os.pathsep}{env.get('PYTHONPATH', '')}"
    env.pop("CI", None)

    result = subprocess.run(
        [sys.executable, "-m", "atdd", "self-upgrade"],
        cwd=str(tmp_path), capture_output=True, text=True, env=env, check=False,
    )

    assert result.returncode == 0, (
        f"`atdd self-upgrade` exited {result.returncode}; it must always exit 0 so a "
        f"post-* hook can never make a completed git operation look broken:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert result.stdout == "", (
        f"`atdd self-upgrade` wrote to stdout, which belongs to git's callers:\n{result.stdout}"
    )
    assert list(tmp_path.iterdir()) == [], (
        f"`atdd self-upgrade` wrote into the working directory: "
        f"{[p.name for p in tmp_path.iterdir()]}"
    )
