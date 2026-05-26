# URN: test:govern-lifecycle:close-substrate-friction-regressions:E026-UNIT-003-bypass-reason-warning-without-reason
# Acceptance: acc:govern-lifecycle:E026-UNIT-003-bypass-reason-warning-without-reason
# WMBT: wmbt:govern-lifecycle:E026
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-003: A remaining bypass flag used without ATDD_BYPASS_REASON prints a
mandatory warning to stderr. The hook must not block (exits 0), but the warning
must name the flag and instruct operators to set ATDD_BYPASS_REASON.

RED state: The pre-push and pre-commit hooks do not yet check for ATDD_BYPASS_REASON.
Tests fail because the warning mechanism has not been implemented.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

HOOKS_DIR = Path(__file__).resolve().parents[1]
HOOK_PATH = HOOKS_DIR / "pre-push"
PRE_COMMIT_PATH = HOOKS_DIR / "pre-commit"

_STDIN_NON_MAIN = (
    "refs/heads/feat/x 0000000000000000000000000000000000000001 "
    "refs/heads/feat/x 0000000000000000000000000000000000000000\n"
)


def _run_pre_push(tmp_path: Path, extra_env: dict) -> subprocess.CompletedProcess:
    hook_dest = tmp_path / "pre-push"
    hook_dest.write_bytes(HOOK_PATH.read_bytes())
    hook_dest.chmod(0o755)

    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "CI": "",
        "ATDD_SKIP_PREPUSH_VALIDATE": "1",
        "ATDD_SKIP_VERSION_GATE": "1",
    }
    env.update(extra_env)

    return subprocess.run(
        [str(hook_dest), "origin", "https://example.com/repo.git"],
        input=_STDIN_NON_MAIN,
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env,
    )


def test_hook_source_contains_bypass_reason_logic():
    """AC-UNIT-003: pre-push hook source must reference ATDD_BYPASS_REASON."""
    text = HOOK_PATH.read_text(encoding="utf-8")
    assert "ATDD_BYPASS_REASON" in text, (
        "pre-push hook does not reference ATDD_BYPASS_REASON.\n"
        "Add a block for each remaining flag that checks ATDD_BYPASS_REASON and "
        "warns when it is absent: "
        "'ATDD WARNING: ATDD_SKIP_<X>=1 used without ATDD_BYPASS_REASON. "
        "Set ATDD_BYPASS_REASON=<reason> to suppress this warning.'"
    )


def test_pre_commit_source_contains_bypass_reason_logic():
    """AC-UNIT-003: pre-commit hook source must reference ATDD_BYPASS_REASON."""
    text = PRE_COMMIT_PATH.read_text(encoding="utf-8")
    assert "ATDD_BYPASS_REASON" in text, (
        "pre-commit hook does not reference ATDD_BYPASS_REASON.\n"
        "Add ATDD_BYPASS_REASON check to the ATDD_SKIP_MANIFEST_CHECK block."
    )


def test_skip_bare_check_without_reason_warns(tmp_path: Path):
    """AC-UNIT-003: ATDD_SKIP_BARE_CHECK without ATDD_BYPASS_REASON prints a warning."""
    if "ATDD_BYPASS_REASON" not in HOOK_PATH.read_text():
        pytest.skip("ATDD_BYPASS_REASON not yet implemented — RED")

    result = _run_pre_push(tmp_path, {"ATDD_SKIP_BARE_CHECK": "1"})
    assert result.returncode == 0, (
        f"Hook must not block when reason is missing; got exit {result.returncode}.\n"
        f"stderr: {result.stderr}"
    )
    assert "ATDD_BYPASS_REASON" in result.stderr, (
        "Expected a warning referencing ATDD_BYPASS_REASON in stderr, got:\n"
        f"{result.stderr}"
    )
    assert "ATDD_SKIP_BARE_CHECK" in result.stderr, (
        "Warning must name the flag being bypassed (ATDD_SKIP_BARE_CHECK).\n"
        f"stderr: {result.stderr}"
    )


def test_skip_bare_check_with_reason_no_warning(tmp_path: Path):
    """AC-UNIT-003: ATDD_SKIP_BARE_CHECK + ATDD_BYPASS_REASON suppresses the reason warning."""
    if "ATDD_BYPASS_REASON" not in HOOK_PATH.read_text():
        pytest.skip("ATDD_BYPASS_REASON not yet implemented — RED")

    result = _run_pre_push(
        tmp_path,
        {"ATDD_SKIP_BARE_CHECK": "1", "ATDD_BYPASS_REASON": "manual test"},
    )
    assert result.returncode == 0
    # The bypass-reason warning should not appear when reason is provided
    assert "Set ATDD_BYPASS_REASON" not in result.stderr, (
        "Reason warning should be suppressed when ATDD_BYPASS_REASON is set.\n"
        f"stderr: {result.stderr}"
    )
