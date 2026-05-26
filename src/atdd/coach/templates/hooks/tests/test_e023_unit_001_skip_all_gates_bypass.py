# URN: test:govern-lifecycle:close-substrate-friction-regressions:E023-UNIT-001-skip-all-gates-sets-all-four-flags
# Acceptance: acc:govern-lifecycle:E023-UNIT-001-skip-all-gates-sets-all-four-flags
# WMBT: wmbt:govern-lifecycle:E023
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-001: ATDD_SKIP_ALL_GATES=1 causes the pre-push hook to bypass bare-check,
version gate, prepush-validate, and registry-check in one shot.

RED state: The pre-push hook template does not yet handle ATDD_SKIP_ALL_GATES=1.
This test fails because the meta-bypass env var is absent.
"""
from __future__ import annotations

import subprocess
import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOK_PATH = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "hooks" / "pre-push"

_BYPASS_NOTICE = "ATDD_SKIP_ALL_GATES"
_GATE_STRINGS = [
    "ATDD_SKIP_BARE_CHECK",
    "ATDD_SKIP_VERSION_GATE",
    "ATDD_SKIP_PREPUSH_VALIDATE",
    "ATDD_SKIP_REGISTRY_CHECK",
]


def test_pre_push_hook_supports_skip_all_gates():
    """AC-UNIT-001: pre-push hook must support ATDD_SKIP_ALL_GATES=1 as a meta-bypass."""
    hook_text = HOOK_PATH.read_text(encoding="utf-8")
    assert "ATDD_SKIP_ALL_GATES" in hook_text, (
        f"Pre-push hook at {HOOK_PATH} does not handle ATDD_SKIP_ALL_GATES.\n"
        "Add a block at the top of the hook that sets all four gate-skip vars when\n"
        "ATDD_SKIP_ALL_GATES=1 is in the environment (issue #845 Item B)."
    )


def test_pre_push_hook_skip_all_gates_exits_zero(tmp_path: Path):
    """AC-UNIT-001: hook exits 0 when ATDD_SKIP_ALL_GATES=1, regardless of other gate states."""
    hook_text = HOOK_PATH.read_text(encoding="utf-8")
    if "ATDD_SKIP_ALL_GATES" not in hook_text:
        pytest.skip("ATDD_SKIP_ALL_GATES not yet implemented in hook — RED")

    hook_dest = tmp_path / "pre-push"
    hook_dest.write_text(hook_text)
    hook_dest.chmod(0o755)

    stdin_payload = (
        "refs/heads/feat/x 0000000000000000000000000000000000000000 "
        "refs/heads/feat/x 1111111111111111111111111111111111111111\n"
    )

    env = os.environ.copy()
    env["ATDD_SKIP_ALL_GATES"] = "1"
    env["CI"] = ""

    result = subprocess.run(
        [str(hook_dest), "origin", "https://example.com/repo.git"],
        input=stdin_payload,
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env,
    )
    assert result.returncode == 0, (
        f"Pre-push hook exited {result.returncode} when ATDD_SKIP_ALL_GATES=1.\n"
        f"stderr: {result.stderr}\nstdout: {result.stdout}"
    )
    assert "ATDD_SKIP_ALL_GATES" in result.stderr or "bypass" in result.stderr.lower(), (
        "Hook did not print a bypass notice to stderr when ATDD_SKIP_ALL_GATES=1.\n"
        f"stderr: {result.stderr}"
    )
