# URN: test:integration-hardening:run-upgrade-unattended:E009-UNIT-001-a-failed-self-upgrade-never-affects-the-git-operation
# Acceptance: acc:integration-hardening:E009-UNIT-001-a-failed-self-upgrade-never-affects-the-git-operation
# WMBT: wmbt:integration-hardening:E009
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""E009-UNIT-001 — prove the mechanism can FAIL, not just that it can pass.

RED Test for acc:integration-hardening:E009-UNIT-001-a-failed-self-upgrade-never-affects-the-git-operation
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:E009

The whole safety claim of #1762 is "an upgrade here cannot affect the operation
it follows". A test that patches ``auto_upgrade`` and asserts it was called
proves none of that — it proves only the happy path, which is the path nobody
worries about. So every assertion below runs with ``auto_upgrade`` **broken**,
in each of the three shapes it can break in, and additionally with the real
``post-merge`` hook script executed by a real ``/bin/sh`` against a real
temporary repository.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

import atdd.coach.commands.upgrader as upgrader

pytestmark = [pytest.mark.coach, pytest.mark.platform]


HOOKS_DIR = Path(upgrader.__file__).resolve().parent.parent / "templates" / "hooks"

#: The three shapes a broken upgrade arrives in. ``(False, "")`` is included
#: deliberately: an upgrade that fails and says nothing is the #1671 defect
#: class, and the hook must survive it just as cleanly as an exception.
_FAILURE_SHAPES = [
    pytest.param({"side_effect": RuntimeError("pip exploded")}, id="raises"),
    pytest.param({"return_value": (False, "externally-managed-environment")}, id="returns-false"),
    pytest.param({"return_value": (False, "")}, id="returns-false-with-no-detail"),
]


def _outdated(**auto_upgrade_kwargs):
    """Context managers putting the module in "an upgrade is genuinely pending".

    Both the cached resolver and the authoritative version probe are pinned, so
    the path under test is actually entered rather than declined early — the
    failure has to be reachable for the test to mean anything.
    """
    return (
        patch.object(upgrader, "_resolve_latest_version", return_value="9.9.9"),
        patch.object(upgrader, "_gate_version", return_value="4.0.0"),
        patch.object(upgrader, "auto_upgrade", **auto_upgrade_kwargs),
    )


@pytest.mark.parametrize("shape", _FAILURE_SHAPES)
def test_e009_unit_001_no_failure_shape_escapes_as_an_exception(shape, capsys):
    """Nothing raises, whatever auto_upgrade does. The caller cannot fail."""
    resolver, probe, upgrade = _outdated(**shape)
    with resolver, probe, upgrade:
        outcome = upgrader.self_upgrade()

    assert outcome == upgrader.SELF_UPGRADE_FAILED, (
        f"a broken upgrade must report {upgrader.SELF_UPGRADE_FAILED!r}, got {outcome!r}"
    )
    captured = capsys.readouterr()
    assert captured.out == "", (
        "a post-* hook's stdout belongs to whatever parses git's output; the "
        f"self-upgrade wrote to it:\n{captured.out}"
    )
    assert "unaffected" in captured.err, (
        f"the failure must say the git operation was unaffected; stderr was:\n{captured.err}"
    )


@pytest.mark.parametrize("shape", _FAILURE_SHAPES)
def test_e009_unit_001_the_reason_is_reported_never_swallowed(shape, capsys):
    """A failure names its reason. A bare 'Upgrade failed' is the #1671 defect."""
    resolver, probe, upgrade = _outdated(**shape)
    with resolver, probe, upgrade:
        upgrader.self_upgrade()

    stderr = capsys.readouterr().err
    assert stderr.strip(), "a failed self-upgrade must not be silent"
    reason_present = (
        "pip exploded" in stderr
        or "externally-managed-environment" in stderr
        or "no reason given" in stderr
    )
    assert reason_present, (
        f"the underlying reason must travel to the reader; stderr was:\n{stderr}"
    )


def test_e009_unit_001_the_cli_seam_always_reports_success(capsys):
    """``atdd self-upgrade`` exits 0 even when the upgrade underneath failed.

    Git has already discarded the exit status by the time it would see one, and
    a non-zero code here would only make a completed pull look broken.
    """
    resolver, probe, upgrade = _outdated(side_effect=RuntimeError("pip exploded"))
    with resolver, probe, upgrade:
        assert upgrader.run_self_upgrade() == 0

    assert capsys.readouterr().out == "", "run_self_upgrade must leave stdout alone"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=False,
    )


@pytest.fixture()
def repo_with_post_merge_hook(tmp_path: Path) -> Path:
    """A real git repo whose post-merge hook is the packaged template.

    ``core.hooksPath`` is deliberately NOT used: it is a shared key across every
    worktree and an unscoped write to it caused #793. The hook is installed by
    copying it into this throwaway repo's own ``.git/hooks/``.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    (repo / "seed.txt").write_text("seed\n")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-qm", "seed")

    installed = repo / ".git" / "hooks" / "post-merge"
    installed.write_text((HOOKS_DIR / "post-merge").read_text(encoding="utf-8"))
    installed.chmod(installed.stat().st_mode | stat.S_IEXEC)
    return repo


@pytest.fixture()
def atdd_stub_dir(tmp_path: Path) -> Path:
    """A directory holding a fake ``atdd`` whose self-upgrade fails loudly.

    The hook's contract is with the *command*, not with the Python function, so
    the stub is the honest injection point: it reproduces the worst case the
    real command is designed never to produce — a non-zero exit with noise on
    both streams — and lets the hook be judged on what it does about it.
    """
    bin_dir = tmp_path / "_stub_bin"
    bin_dir.mkdir()
    script = bin_dir / "atdd"
    script.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = 'self-upgrade' ]; then\n"
        "  echo 'STUB: self-upgrade blew up' >&2\n"
        "  exit 3\n"
        "fi\n"
        "exit 0\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def test_e009_unit_001_a_real_merge_completes_when_the_hook_upgrade_fails(
    repo_with_post_merge_hook: Path, atdd_stub_dir: Path,
):
    """The end that matters: a real `git merge` with a hook that fails outright.

    git ignores a post-merge hook's exit code by its own contract. This asserts
    that contract against a real git rather than trusting the documentation,
    because the entire argument for moving the upgrade here rests on it.
    """
    repo = repo_with_post_merge_hook

    _git(repo, "checkout", "-q", "-b", "topic")
    (repo / "topic.txt").write_text("topic\n")
    _git(repo, "add", "topic.txt")
    _git(repo, "commit", "-qm", "topic work")
    _git(repo, "checkout", "-q", "main")

    env = dict(os.environ)
    env["PATH"] = f"{atdd_stub_dir}{os.pathsep}{env['PATH']}"
    env.pop("CI", None)  # the hooks no-op under CI; this must exercise the real path

    before = _git(repo, "config", "--get", "core.hooksPath").stdout
    merged = subprocess.run(
        ["git", "merge", "--no-ff", "-m", "merge topic", "topic"],
        cwd=str(repo), capture_output=True, text=True, env=env, check=False,
    )

    assert merged.returncode == 0, (
        "git must ignore the post-merge hook's exit code — the merge was refused:\n"
        f"stdout:\n{merged.stdout}\nstderr:\n{merged.stderr}"
    )
    assert (repo / "topic.txt").exists(), "the merge did not actually land"
    assert "STUB: self-upgrade blew up" not in merged.stdout, (
        "hook output reached the stdout git's callers parse"
    )
    assert _git(repo, "config", "--get", "core.hooksPath").stdout == before, (
        "the self-upgrade path must not write core.hooksPath (#793)"
    )
    assert _git(repo, "status", "--porcelain").stdout == "", (
        "the self-upgrade left a file in the working tree:\n"
        f"{_git(repo, 'status', '--porcelain').stdout}"
    )
