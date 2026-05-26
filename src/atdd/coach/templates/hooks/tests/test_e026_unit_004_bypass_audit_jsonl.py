# URN: test:govern-lifecycle:close-substrate-friction-regressions:E026-UNIT-004-bypass-audit-jsonl-written
# Acceptance: acc:govern-lifecycle:E026-UNIT-004-bypass-audit-jsonl-written
# WMBT: wmbt:govern-lifecycle:E026
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-004 (superseded by E030): E026 required hooks to write bypass-audit.jsonl.
E030 (2026-05-26) retires all bypass flags; bypass-audit.jsonl is no longer written
by hooks. These tests are updated to assert ABSENCE of bypass-audit.jsonl writing
— serving as regression guards against re-introduction of the audit mechanism.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

HOOKS_DIR = Path(__file__).resolve().parents[1]
HOOK_PATH = HOOKS_DIR / "pre-push"

_STDIN_NON_MAIN = (
    "refs/heads/feat/x 0000000000000000000000000000000000000001 "
    "refs/heads/feat/x 0000000000000000000000000000000000000000\n"
)

_REQUIRED_JSONL_FIELDS = {"timestamp", "flag", "reason", "hook"}


def _run_hook_with_bypass(tmp_path: Path, flag: str, reason: str) -> Path:
    """Install hook, create .atdd/ dir, run with flag+reason, return jsonl path."""
    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()

    hook_dest = tmp_path / "pre-push"
    hook_dest.write_bytes(HOOK_PATH.read_bytes())
    hook_dest.chmod(0o755)

    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "CI": "",
        "ATDD_SKIP_PREPUSH_VALIDATE": "1",
        "ATDD_SKIP_VERSION_GATE": "1",
        "ATDD_SKIP_BARE_CHECK": "1",
        "ATDD_BYPASS_REASON": reason,
        flag: "1",
        "ATDD_REPO_ROOT": str(tmp_path),
    }

    subprocess.run(
        [str(hook_dest), "origin", "https://example.com/repo.git"],
        input=_STDIN_NON_MAIN,
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env,
    )

    return atdd_dir / "bypass-audit.jsonl"


def test_hook_source_does_not_contain_bypass_audit_jsonl():
    """E030 regression guard: pre-push hook must NOT reference bypass-audit.jsonl."""
    text = HOOK_PATH.read_text(encoding="utf-8")
    assert "bypass-audit.jsonl" not in text, (
        "pre-push hook still references bypass-audit.jsonl.\n"
        "E030 retires all bypass flags; bypass-audit.jsonl writing must be removed."
    )


def test_commit_msg_hook_does_not_reference_bypass_audit_jsonl():
    """E030 regression guard: commit-msg hook must NOT reference bypass-audit.jsonl."""
    text = (HOOKS_DIR / "commit-msg").read_text(encoding="utf-8")
    assert "bypass-audit.jsonl" not in text, (
        "commit-msg hook still references bypass-audit.jsonl.\n"
        "E030 retires ATDD_SKIP_MASSDELETE; remove the bypass-audit.jsonl write."
    )


def test_pre_commit_hook_does_not_reference_bypass_audit_jsonl():
    """E030 regression guard: pre-commit hook must NOT reference bypass-audit.jsonl."""
    text = (HOOKS_DIR / "pre-commit").read_text(encoding="utf-8")
    assert "bypass-audit.jsonl" not in text, (
        "pre-commit hook still references bypass-audit.jsonl.\n"
        "E030 retires ATDD_SKIP_MANIFEST_CHECK; remove the bypass-audit.jsonl write."
    )
