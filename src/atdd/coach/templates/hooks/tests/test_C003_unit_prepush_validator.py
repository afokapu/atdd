# Acceptance: acc:integration-hardening:C003-UNIT-001-prepush-blocks-on-coder-validator-failure
# Acceptance: acc:integration-hardening:C003-UNIT-002-prepush-blocks-on-coach-validator-failure
# Acceptance: acc:integration-hardening:C003-UNIT-003-prepush-skipped-in-ci
# Acceptance: acc:integration-hardening:C003-UNIT-004-prepush-fast-path-no-atdd-files
"""Unit tests for the pre-push blocking validator pass (#583).

Background: the pre-push hook was advisory-only (exits 0 always).  Agents
repeatedly trip silent-swallow / boundary / rule-id-coherence validators
*after* push, burning 1-2 CI cycles per PR (evidence in issue #583).

These tests verify the new blocking validator section:
- Files in src/atdd/coder/** or src/atdd/coach/** trigger the matching
  validator phase (--local --skip-api).
- A non-zero validator exit causes the hook to exit non-zero (blocks push).
- ATDD_SKIP_PREPUSH_VALIDATE=1 bypasses the validator section entirely.
- CI=true bypasses the validator section (CI already runs full validate).
- Pushes with no ATDD source files skip the validator section entirely.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOK_PATH = REPO_ROOT / "src/atdd/coach/templates/hooks/pre-push"


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
    """Commit staged changes and return HEAD SHA."""
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
    """Write a placeholder file, stage it, commit, return HEAD SHA."""
    target = path / relative_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# placeholder\n")
    subprocess.run(
        ["git", "-C", str(path), "add", relative_file],
        check=True,
        capture_output=True,
    )
    return _commit(path, message)


def _run_hook(
    repo: Path,
    local_sha: str,
    remote_sha: str,
    *,
    fake_atdd_dir: Path | None = None,
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    """Execute the pre-push hook for a feature-branch push.

    stdin format: local_ref local_sha remote_ref remote_sha
    CI=true and ATDD_SKIP_VERSION_GATE=1 bypass the unrelated version gate.
    """
    push_stdin = (
        f"refs/heads/feat/test-c003 {local_sha} "
        f"refs/heads/feat/test-c003 {remote_sha}\n"
    )
    env = {
        **os.environ,
        "ATDD_SKIP_VERSION_GATE": "1",  # bypass version gate
        "ATDD_SKIP_BARE_CHECK": "1",    # we don't test bare-mode here
        # NOTE: deliberately do NOT set CI=true — the validator section
        # is skipped when CI=true, so tests that exercise it must not set it.
    }
    if fake_atdd_dir is not None:
        env["PATH"] = f"{fake_atdd_dir}:{os.environ['PATH']}"
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        ["sh", str(HOOK_PATH), "origin", "https://example.invalid/x.git"],
        cwd=str(repo),
        input=push_stdin,
        env=env,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_prepush_blocks_when_coder_file_changed_and_validator_fails(
    tmp_path: Path,
    fake_atdd_failing_coder: Path,
) -> None:
    """C003-UNIT-001: push with a coder-phase file change + failing validator is blocked."""
    _init_repo(tmp_path)
    base_sha = _add_and_commit(tmp_path, "README.md", "seed")
    tip_sha = _add_and_commit(
        tmp_path,
        "src/atdd/coder/validators/test_foo.py",
        "add coder validator",
    )

    result = _run_hook(
        tmp_path,
        local_sha=tip_sha,
        remote_sha=base_sha,
        fake_atdd_dir=fake_atdd_failing_coder,
    )

    assert result.returncode != 0, (
        f"pre-push must exit non-zero when coder validator fails; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )
    assert "validate" in result.stderr.lower() or "atdd" in result.stderr.lower(), (
        f"stderr must reference the validator failure; got:\n{result.stderr}"
    )


def test_prepush_skip_env_overrides_validator_block(
    tmp_path: Path,
    fake_atdd_failing_coder: Path,
) -> None:
    """C003-UNIT-001 (E030 regression): ATDD_SKIP_PREPUSH_VALIDATE=1 is retired; hook blocks regardless."""
    _init_repo(tmp_path)
    base_sha = _add_and_commit(tmp_path, "README.md", "seed")
    tip_sha = _add_and_commit(
        tmp_path,
        "src/atdd/coder/validators/test_foo.py",
        "add coder validator",
    )

    result = _run_hook(
        tmp_path,
        local_sha=tip_sha,
        remote_sha=base_sha,
        fake_atdd_dir=fake_atdd_failing_coder,
        extra_env={"ATDD_SKIP_PREPUSH_VALIDATE": "1"},
    )

    # E030 (2026-05-26): ATDD_SKIP_PREPUSH_VALIDATE retired unconditionally.
    # The env var is ignored; the blocking validator must still fire.
    assert result.returncode != 0, (
        f"ATDD_SKIP_PREPUSH_VALIDATE=1 must be ignored (E030); hook must still block; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )


def test_prepush_blocks_when_coach_file_changed_and_validator_fails(
    tmp_path: Path,
    fake_atdd_failing_coach: Path,
) -> None:
    """C003-UNIT-002: push with a coach-phase file change + failing validator is blocked."""
    _init_repo(tmp_path)
    base_sha = _add_and_commit(tmp_path, "README.md", "seed")
    tip_sha = _add_and_commit(
        tmp_path,
        "src/atdd/coach/commands/new_command.py",
        "add coach command",
    )

    result = _run_hook(
        tmp_path,
        local_sha=tip_sha,
        remote_sha=base_sha,
        fake_atdd_dir=fake_atdd_failing_coach,
    )

    assert result.returncode != 0, (
        f"pre-push must exit non-zero when coach validator fails; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )


def test_prepush_validator_skipped_when_ci_true(
    tmp_path: Path,
    fake_atdd_failing_coder: Path,
) -> None:
    """C003-UNIT-003: CI=true causes the validator section to be bypassed."""
    _init_repo(tmp_path)
    base_sha = _add_and_commit(tmp_path, "README.md", "seed")
    tip_sha = _add_and_commit(
        tmp_path,
        "src/atdd/coder/validators/test_foo.py",
        "add coder validator",
    )

    # Pass fake_atdd_dir but also force CI=true to override the unset.
    env = {
        **os.environ,
        "CI": "true",
        "ATDD_SKIP_VERSION_GATE": "1",
        "ATDD_SKIP_BARE_CHECK": "1",
        "PATH": f"{fake_atdd_failing_coder}:{os.environ['PATH']}",
    }
    result = subprocess.run(
        ["sh", str(HOOK_PATH), "origin", "https://example.invalid/x.git"],
        cwd=str(tmp_path),
        input=(
            f"refs/heads/feat/test-c003 {tip_sha} "
            f"refs/heads/feat/test-c003 {base_sha}\n"
        ),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"CI=true must bypass the blocking validator pass; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )


def test_prepush_fast_path_no_atdd_files(
    tmp_path: Path,
    fake_atdd_failing_coder: Path,
) -> None:
    """C003-UNIT-004: push with no ATDD source files skips validators entirely."""
    _init_repo(tmp_path)
    base_sha = _add_and_commit(tmp_path, "README.md", "seed")
    tip_sha = _add_and_commit(
        tmp_path,
        "python/app.py",   # non-ATDD file
        "add app",
    )

    result = _run_hook(
        tmp_path,
        local_sha=tip_sha,
        remote_sha=base_sha,
        fake_atdd_dir=fake_atdd_failing_coder,
    )

    # Even though fake_atdd would fail on 'validate coder', it must NOT be
    # invoked when no ATDD source files appear in the diff.
    assert result.returncode == 0, (
        f"pre-push must not block when no ATDD source files changed; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )
    assert "FAKE ATDD" not in result.stderr, (
        f"fake atdd must not have been invoked; stderr:\n{result.stderr}"
    )


def test_prepush_passes_when_validator_succeeds(
    tmp_path: Path,
    fake_atdd_passing: Path,
) -> None:
    """C003-UNIT-001 (positive): push with coder file changed but passing validator exits 0."""
    _init_repo(tmp_path)
    base_sha = _add_and_commit(tmp_path, "README.md", "seed")
    tip_sha = _add_and_commit(
        tmp_path,
        "src/atdd/coder/validators/test_bar.py",
        "add coder file",
    )

    result = _run_hook(
        tmp_path,
        local_sha=tip_sha,
        remote_sha=base_sha,
        fake_atdd_dir=fake_atdd_passing,
    )

    assert result.returncode == 0, (
        f"pre-push must exit 0 when validator passes; "
        f"rc={result.returncode}\nstderr={result.stderr}"
    )


# ---------------------------------------------------------------------------
# #1254: the heavy `atdd repo validate` URN-graph traversal is trimmed from the
# LOCAL pre-push RUN_REPO leg — deferred to CI by default, opt-in via
# ATDD_PREPUSH_FULL=1. Source-text guards (the executable behavioral coverage
# lives in the CI-collected
# src/atdd/coach/validators/test_prepush_repo_validate_opt_in.py).
# ---------------------------------------------------------------------------


def test_repo_validate_leg_is_opt_in_via_prepush_full() -> None:
    """#1254: the full `atdd repo validate` traversal in the RUN_REPO leg must be
    guarded by ATDD_PREPUSH_FULL, not invoked unconditionally."""
    text = HOOK_PATH.read_text(encoding="utf-8")
    assert "atdd repo validate" in text, (
        "RUN_REPO leg removed entirely — expected an opt-in guard, not removal."
    )
    assert "ATDD_PREPUSH_FULL" in text, (
        "the full `atdd repo validate` traversal must be opt-in via ATDD_PREPUSH_FULL=1 "
        "(deferred to CI by default); the guard is missing from the pre-push hook."
    )
    assert text.index("ATDD_PREPUSH_FULL") < text.index("atdd repo validate >&2"), (
        "the ATDD_PREPUSH_FULL guard must precede (wrap) the `atdd repo validate` invocation."
    )


def test_repo_validate_trim_introduces_no_skip_bypass() -> None:
    """#1254: the trim adds an opt-IN flag; it must not introduce any ATDD_SKIP_* bypass."""
    text = HOOK_PATH.read_text(encoding="utf-8")
    assert "ATDD_SKIP_PREPUSH" not in text and "ATDD_SKIP_REPO" not in text, (
        "ATDD_PREPUSH_FULL adds validation; it must not be paired with an ATDD_SKIP_* bypass."
    )
