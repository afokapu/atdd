# Acceptance: acc:integration-hardening:M002-UNIT-001-postcommit-runs-validate-planner-on-plan-changes
# Acceptance: acc:integration-hardening:M002-UNIT-002-prepush-runs-validate-planner-on-plan-changes
# Acceptance: acc:integration-hardening:M002-INTEGRATION-001-prepush-blocks-invalid-wmbt-letter
# Acceptance: acc:integration-hardening:M002-SMOKE-001-prepush-hook-fires-on-real-git-push
"""Unit + integration tests for plan/** → validate planner routing in hooks (#642).

Background: the post-commit and pre-push hooks mapped plan/** to
`atdd repo validate` ONLY.  Agents could commit plan/X/U001.yaml (invalid
step-code letter) and all three local hooks passed, leaving CI to catch the
violation after push — burning 1-2 CI cycles per PR.

Evidence: PR #640 (#628 watcher) committed plan/coach_ops/U001.yaml on
2026-05-12; post-commit and pre-push both passed; CI's validate-planner
job caught the step-code + lens + wagon schema errors.

These tests verify that plan/** changes now also trigger
`atdd validate planner --local --skip-api` in both hooks.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest


pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[6]
POST_COMMIT_PATH = REPO_ROOT / "src/atdd/coach/templates/hooks/post-commit"
PRE_PUSH_PATH = REPO_ROOT / "src/atdd/coach/templates/hooks/pre-push"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_repo(path: Path) -> None:
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(path)],
        check=True,
        capture_output=True,
    )
    for k, v in (("user.email", "test@atdd.test"), ("user.name", "atdd test")):
        subprocess.run(
            ["git", "-C", str(path), "config", k, v],
            check=True,
            capture_output=True,
        )


def _commit(path: Path, message: str) -> str:
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", message],
        check=True,
        capture_output=True,
    )
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _add_and_commit(path: Path, relative_file: str, message: str) -> str:
    target = path / relative_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# placeholder\n")
    subprocess.run(
        ["git", "-C", str(path), "add", relative_file],
        check=True,
        capture_output=True,
    )
    return _commit(path, message)


def _make_fake_atdd(tmp_path: Path, subdir: str, script_body: str) -> Path:
    """Write a fake atdd binary into a fresh sub-directory and make it executable."""
    bin_dir = tmp_path / subdir
    bin_dir.mkdir()
    script = bin_dir / "atdd"
    script.write_text("#!/bin/sh\n" + script_body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _run_post_commit(repo: Path, fake_atdd_dir: Path | None = None) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "ATDD_SKIP_POSTCOMMIT": "0",
        # do NOT set CI=true — that would bypass the hook entirely
    }
    if fake_atdd_dir is not None:
        env["PATH"] = f"{fake_atdd_dir}:{os.environ['PATH']}"
    return subprocess.run(
        ["sh", str(POST_COMMIT_PATH)],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
    )


def _run_pre_push(
    repo: Path,
    local_sha: str,
    remote_sha: str,
    fake_atdd_dir: Path | None = None,
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    push_stdin = (
        f"refs/heads/feat/test-m002 {local_sha} "
        f"refs/heads/feat/test-m002 {remote_sha}\n"
    )
    env = {
        **os.environ,
        "ATDD_SKIP_VERSION_GATE": "1",
        "ATDD_SKIP_BARE_CHECK": "1",
    }
    if fake_atdd_dir is not None:
        env["PATH"] = f"{fake_atdd_dir}:{os.environ['PATH']}"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["sh", str(PRE_PUSH_PATH), "origin", "https://example.invalid/x.git"],
        cwd=str(repo),
        input=push_stdin,
        env=env,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Fake atdd fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_atdd_recording(tmp_path: Path) -> tuple[Path, Path]:
    """Fake atdd that records every call to a log file; always exits 0.

    Returns (bin_dir, log_file).
    """
    log_file = tmp_path / "atdd_calls.log"
    bin_dir = _make_fake_atdd(
        tmp_path,
        "_fake_atdd_record",
        f'echo "$@" >> "{log_file}"\nexit 0\n',
    )
    return bin_dir, log_file


@pytest.fixture()
def fake_atdd_failing_planner(tmp_path: Path) -> Path:
    """Fake atdd that exits 1 for 'validate planner', exits 0 for everything else."""
    return _make_fake_atdd(
        tmp_path,
        "_fake_atdd_fail_planner",
        "if [ \"$1\" = 'validate' ] && [ \"$2\" = 'planner' ]; then\n"
        "  echo 'FAKE ATDD: validate planner FAILED — invalid step code U001' >&2\n"
        "  exit 1\n"
        "fi\n"
        "exit 0\n",
    )


# ---------------------------------------------------------------------------
# M002-UNIT-001: post-commit invokes validate planner on plan/** changes
# ---------------------------------------------------------------------------


def test_postcommit_invokes_validate_planner_on_plan_file(
    tmp_path: Path,
    fake_atdd_recording: tuple[Path, Path],
) -> None:
    """M002-UNIT-001: post-commit runs 'validate planner' when plan/** is committed."""
    fake_atdd_dir, log_file = fake_atdd_recording
    _init_repo(tmp_path)
    _add_and_commit(tmp_path, "plan/coach_ops/M001.yaml", "add plan file")

    result = _run_post_commit(tmp_path, fake_atdd_dir)

    assert result.returncode == 0, (
        f"post-commit must exit 0 (info-only); rc={result.returncode}\n"
        f"stderr={result.stderr}"
    )
    calls = log_file.read_text() if log_file.exists() else ""
    assert "validate planner" in calls, (
        f"post-commit must invoke 'atdd validate planner' for plan/** changes; "
        f"recorded calls:\n{calls}"
    )


def test_postcommit_does_not_invoke_validate_planner_for_src_only(
    tmp_path: Path,
    fake_atdd_recording: tuple[Path, Path],
) -> None:
    """M002-UNIT-001 (negative): post-commit does NOT invoke validate planner for src/ changes."""
    fake_atdd_dir, log_file = fake_atdd_recording
    _init_repo(tmp_path)
    _add_and_commit(tmp_path, "src/myapp/utils.py", "add util")

    _run_post_commit(tmp_path, fake_atdd_dir)

    calls = log_file.read_text() if log_file.exists() else ""
    assert "validate planner" not in calls, (
        f"post-commit must NOT invoke 'atdd validate planner' for src/ changes; "
        f"recorded calls:\n{calls}"
    )


# ---------------------------------------------------------------------------
# M002-UNIT-002: pre-push blocks on plan/** when validate planner fails
# ---------------------------------------------------------------------------


def test_prepush_blocks_when_plan_file_changed_and_validator_fails(
    tmp_path: Path,
    fake_atdd_failing_planner: Path,
) -> None:
    """M002-UNIT-002: pre-push exits non-zero when plan/** changed and validate planner fails."""
    _init_repo(tmp_path)
    base_sha = _add_and_commit(tmp_path, "README.md", "seed")
    tip_sha = _add_and_commit(tmp_path, "plan/coach_ops/M001.yaml", "add plan file")

    result = _run_pre_push(
        tmp_path,
        local_sha=tip_sha,
        remote_sha=base_sha,
        fake_atdd_dir=fake_atdd_failing_planner,
    )

    assert result.returncode != 0, (
        f"pre-push must exit non-zero when plan/** changed and validate planner fails; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )
    assert "planner" in result.stderr.lower() or "validate" in result.stderr.lower(), (
        f"stderr must reference the planner failure; got:\n{result.stderr}"
    )


def test_prepush_passes_when_plan_file_changed_and_validator_passes(
    tmp_path: Path,
) -> None:
    """M002-UNIT-002 (positive): pre-push exits 0 when plan/** changed and validate planner passes."""
    passing_dir = _make_fake_atdd(
        tmp_path,
        "_fake_pass",
        "exit 0\n",
    )
    _init_repo(tmp_path)
    base_sha = _add_and_commit(tmp_path, "README.md", "seed")
    tip_sha = _add_and_commit(tmp_path, "plan/coach_ops/M001.yaml", "add plan file")

    result = _run_pre_push(
        tmp_path,
        local_sha=tip_sha,
        remote_sha=base_sha,
        fake_atdd_dir=passing_dir,
    )

    assert result.returncode == 0, (
        f"pre-push must exit 0 when plan/** changed and validate planner passes; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )


def test_prepush_skip_env_overrides_planner_block(
    tmp_path: Path,
    fake_atdd_failing_planner: Path,
) -> None:
    """M002-UNIT-002 (E030 regression): ATDD_SKIP_PREPUSH_VALIDATE=1 is retired; hook blocks regardless."""
    _init_repo(tmp_path)
    base_sha = _add_and_commit(tmp_path, "README.md", "seed")
    tip_sha = _add_and_commit(tmp_path, "plan/coach_ops/M001.yaml", "add plan file")

    result = _run_pre_push(
        tmp_path,
        local_sha=tip_sha,
        remote_sha=base_sha,
        fake_atdd_dir=fake_atdd_failing_planner,
        extra_env={"ATDD_SKIP_PREPUSH_VALIDATE": "1"},
    )

    # E030 (2026-05-26): ATDD_SKIP_PREPUSH_VALIDATE retired unconditionally.
    # The env var is ignored; the blocking planner validator must still fire.
    assert result.returncode != 0, (
        f"ATDD_SKIP_PREPUSH_VALIDATE=1 must be ignored (E030); hook must still block; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )


# ---------------------------------------------------------------------------
# M002-INTEGRATION-001: pre-push blocks when plan/ has invalid step-code letter
# ---------------------------------------------------------------------------


def test_prepush_blocks_invalid_wmbt_step_code_letter_in_plan(
    tmp_path: Path,
    fake_atdd_failing_planner: Path,
) -> None:
    """M002-INTEGRATION-001: pre-push blocks push of plan/X/U001.yaml (U is not a valid step-code).

    The fake atdd validator mimics the real 'validate planner' exit code when
    it encounters an invalid step-code letter in a WMBT file.
    """
    _init_repo(tmp_path)
    base_sha = _add_and_commit(tmp_path, "README.md", "seed")

    # Commit a plan file with an "invalid" name (U is not in M/E/C/D/L/P/Y/R/K).
    tip_sha = _add_and_commit(tmp_path, "plan/coach_ops/U001.yaml", "add invalid wmbt")

    result = _run_pre_push(
        tmp_path,
        local_sha=tip_sha,
        remote_sha=base_sha,
        fake_atdd_dir=fake_atdd_failing_planner,
    )

    assert result.returncode != 0, (
        f"pre-push must block when plan/ contains WMBT with invalid step-code letter; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )
    assert "invalid step code" in result.stderr.lower() or "planner" in result.stderr.lower(), (
        f"stderr must reference the step-code error; got:\n{result.stderr}"
    )
