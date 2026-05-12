# Acceptance: acc:integration-hardening:C003-SMOKE-001-prepush-validator-fires-via-git-push
"""SMOKE test: the blocking validator pass fires via real git push plumbing (#583).

The UNIT tests exercise the hook script in isolation via ``sh hook_path ...``.
This SMOKE test verifies the hook fires through git's own trigger plumbing —
i.e. that the install mode (chmod +x, .git/hooks/pre-push) actually blocks a
real ``git push`` when ATDD source files are in the diff and the validator fails.

Failure modes this catches that UNIT tests miss:
- hook file not executable after installation
- git-supplied env doesn't have the fake atdd on PATH
- git stdin format differs from the test payload
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest


pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOK_PATH = REPO_ROOT / "src/atdd/coach/templates/hooks/pre-push"


def _init_local_and_remote(tmp_path: Path) -> tuple[Path, Path]:
    local = tmp_path / "local"
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "-b", "main", str(local)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True, capture_output=True)
    for k, v in (("user.email", "test@atdd.test"), ("user.name", "atdd test")):
        subprocess.run(["git", "-C", str(local), "config", k, v], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(local), "remote", "add", "origin", str(remote)],
        check=True,
        capture_output=True,
    )
    return local, remote


def _install_hook(local: Path) -> None:
    dst = local / ".git" / "hooks" / "pre-push"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(HOOK_PATH.read_bytes())
    dst.chmod(dst.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _make_seed_and_push_main(local: Path) -> str:
    """Create a seed commit on main, push to origin, return the SHA."""
    (local / "README.md").write_text("hello\n")
    subprocess.run(["git", "-C", str(local), "add", "README.md"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(local), "commit", "-q", "-m", "seed"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(local), "push", "-q", "origin", "main"],
        check=True,
        capture_output=True,
        env={**os.environ, "ATDD_SKIP_VERSION_GATE": "1", "CI": "true"},
    )
    return subprocess.run(
        ["git", "-C", str(local), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _make_feature_commit(local: Path, relative_file: str) -> None:
    target = local / relative_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# fake coder file\n")
    subprocess.run(["git", "-C", str(local), "add", relative_file], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(local), "commit", "-q", "-m", "add atdd file"],
        check=True,
        capture_output=True,
    )


def _make_fake_atdd(tmp_path: Path, *, fails_on: str) -> Path:
    bin_dir = tmp_path / "_fake_atdd_smoke"
    bin_dir.mkdir()
    script = bin_dir / "atdd"
    script.write_text(
        f"#!/bin/sh\n"
        f"if [ \"$1\" = 'validate' ] && [ \"$2\" = '{fails_on}' ]; then\n"
        f"  echo 'FAKE ATDD: validate {fails_on} FAILED' >&2\n"
        f"  exit 1\n"
        f"fi\n"
        f"exit 0\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def test_git_push_blocked_by_validator_via_hook_plumbing(tmp_path: Path) -> None:
    """C003-SMOKE-001: real git push is blocked when ATDD files changed and validator fails."""
    local, _remote = _init_local_and_remote(tmp_path)
    _make_seed_and_push_main(local)
    _install_hook(local)

    # Create a feature branch with a coder-phase file
    subprocess.run(
        ["git", "-C", str(local), "checkout", "-q", "-b", "feat/c003-smoke"],
        check=True,
        capture_output=True,
    )
    _make_feature_commit(local, "src/atdd/coder/validators/test_smoke_target.py")

    fake_atdd = _make_fake_atdd(tmp_path, fails_on="coder")
    env = {
        **os.environ,
        "ATDD_SKIP_VERSION_GATE": "1",
        "ATDD_SKIP_BARE_CHECK": "1",
        "PATH": f"{fake_atdd}:{os.environ['PATH']}",
        # Do NOT set CI=true — we want the validator section to run
    }
    result = subprocess.run(
        ["git", "-C", str(local), "push", "origin", "feat/c003-smoke"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0, (
        f"git push must be blocked when coder validator fails; "
        f"rc={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "validate" in combined.lower() or "atdd" in combined.lower(), (
        f"push rejection must reference the validator; got:\n{combined}"
    )
    # Confirm no refs advanced on remote
    refs = subprocess.run(
        ["git", "-C", str(local), "ls-remote", "origin"],
        capture_output=True,
        text=True,
    ).stdout
    assert "feat/c003-smoke" not in refs, (
        f"remote must not have the feature branch after blocked push; refs:\n{refs}"
    )
