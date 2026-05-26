# URN: test:govern-lifecycle:close-substrate-friction-regressions:E022-UNIT-003-post-commit-restores-core-bare-on-exit
# Acceptance: acc:govern-lifecycle:E022-UNIT-003-post-commit-restores-core-bare-on-exit
# WMBT: wmbt:govern-lifecycle:E022
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-003: post-commit hook template has a shell trap that restores core.bare to
its pre-hook value even when pytest exits non-zero.

RED state: The post-commit hook at src/atdd/coach/templates/hooks/post-commit does not
yet snapshot core.bare before invoking pytest or register an EXIT trap to restore it.
This test fails because the trap is absent.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOK_PATH = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "hooks" / "post-commit"

_SNAPSHOT_PATTERNS = ["BARE_BEFORE", "core.bare", "trap"]


def test_post_commit_hook_has_core_bare_snapshot_and_trap():
    """AC-UNIT-003: post-commit hook must snapshot core.bare and register an EXIT trap."""
    hook_text = HOOK_PATH.read_text(encoding="utf-8")

    has_snapshot = any(p in hook_text for p in ("BARE_BEFORE", "core_bare_before", "bare_snapshot"))
    has_trap = "trap" in hook_text
    has_restore = "core.bare" in hook_text and ("unset" in hook_text or "config" in hook_text)

    missing = []
    if not has_snapshot:
        missing.append("core.bare snapshot variable (e.g., BARE_BEFORE=$(git config core.bare 2>/dev/null || echo ''))")
    if not has_trap:
        missing.append("shell trap on EXIT to restore core.bare")
    if not has_restore:
        missing.append("restore call inside the trap (git config core.bare or git config --unset core.bare)")

    assert not missing, (
        f"Post-commit hook at {HOOK_PATH} is missing:\n"
        + "\n".join(f"  - {m}" for m in missing)
        + "\n\nAdd a snapshot+trap pattern so core.bare is restored even when pytest exits\n"
        "non-zero or is killed mid-run (issue #845 Item A)."
    )
