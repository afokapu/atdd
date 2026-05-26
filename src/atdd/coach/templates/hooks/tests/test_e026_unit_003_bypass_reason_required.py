# URN: test:govern-lifecycle:close-substrate-friction-regressions:E026-UNIT-003-bypass-reason-warning-without-reason
# Acceptance: acc:govern-lifecycle:E026-UNIT-003-bypass-reason-warning-without-reason
# WMBT: wmbt:govern-lifecycle:E026
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-003 (superseded by E030): E026 required ATDD_BYPASS_REASON in hooks.
E030 (2026-05-26 full retirement) removes all bypass flags AND the bypass-reason
mechanism. These tests are updated to assert ABSENCE of ATDD_BYPASS_REASON —
serving as regression guards against re-introduction.
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


def test_hook_source_does_not_contain_bypass_reason():
    """E030 regression guard: pre-push hook must NOT reference ATDD_BYPASS_REASON."""
    text = HOOK_PATH.read_text(encoding="utf-8")
    assert "ATDD_BYPASS_REASON" not in text, (
        "pre-push hook still references ATDD_BYPASS_REASON.\n"
        "E030 retires all ATDD_SKIP_* flags; ATDD_BYPASS_REASON has no callers. "
        "Remove _emit_bypass_audit and all ATDD_BYPASS_REASON references."
    )


def test_pre_commit_source_does_not_contain_bypass_reason():
    """E030 regression guard: pre-commit hook must NOT reference ATDD_BYPASS_REASON."""
    text = PRE_COMMIT_PATH.read_text(encoding="utf-8")
    assert "ATDD_BYPASS_REASON" not in text, (
        "pre-commit hook still references ATDD_BYPASS_REASON.\n"
        "E030 retires ATDD_SKIP_MANIFEST_CHECK; remove the ATDD_BYPASS_REASON block."
    )


def test_skip_bare_check_env_var_has_no_effect(tmp_path: Path):
    """E030 regression guard: ATDD_SKIP_BARE_CHECK env var must not be recognised by hook."""
    hook_text = HOOK_PATH.read_text(encoding="utf-8")
    assert "ATDD_SKIP_BARE_CHECK" not in hook_text, (
        "pre-push hook still checks ATDD_SKIP_BARE_CHECK.\n"
        "E030 retires this flag unconditionally; remove the env-var check block."
    )


def test_skip_prepush_validate_env_var_has_no_effect(tmp_path: Path):
    """E030 regression guard: ATDD_SKIP_PREPUSH_VALIDATE must not be in hook source."""
    hook_text = HOOK_PATH.read_text(encoding="utf-8")
    assert "ATDD_SKIP_PREPUSH_VALIDATE" not in hook_text, (
        "pre-push hook still checks ATDD_SKIP_PREPUSH_VALIDATE.\n"
        "E030 retires this flag unconditionally; remove the env-var check block."
    )
