# URN: test:govern-lifecycle:close-substrate-friction-regressions:E023-SMOKE-001-routine-push-requires-zero-gate-bypasses
# Acceptance: acc:govern-lifecycle:E023-SMOKE-001-routine-push-requires-zero-gate-bypasses
# WMBT: wmbt:govern-lifecycle:E023
# Phase: RED
# Layer: backend.integration
"""
AC-SMOKE-001: a routine branch push on an up-to-date worktree completes without
any env-var bypass.

RED state: Currently a routine push triggers 1+ gates (version gate fires when
installed atdd < PyPI latest; registry check blocks on drift). This test stub
is written RED and will pass only after E023's implementation ships.
"""
from __future__ import annotations

import subprocess
import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.slow]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOK_PATH = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "hooks" / "pre-push"


def test_pre_push_hook_docs_claim_zero_bypasses_for_clean_state():
    """AC-SMOKE-001 (structural): hook must document that zero bypasses are needed for clean push."""
    hook_text = HOOK_PATH.read_text(encoding="utf-8")
    # In GREEN state the hook will have ATDD_SKIP_ALL_GATES + auto-heal registry.
    # For now verify that ATDD_SKIP_ALL_GATES exists (RED: this will fail).
    assert "ATDD_SKIP_ALL_GATES" in hook_text, (
        "Pre-push hook does not yet have ATDD_SKIP_ALL_GATES support.\n"
        "The full SMOKE (routine push with zero bypasses) requires E023 implementation.\n"
        "This test drives the implementation (issue #845 Item B)."
    )
