# URN: test:govern-lifecycle:close-substrate-friction-regressions:E022-UNIT-001-post-commit-hook-excludes-slow-marker
# Acceptance: acc:govern-lifecycle:E022-UNIT-001-post-commit-hook-excludes-slow-marker
# WMBT: wmbt:govern-lifecycle:E022
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-001: post-commit hook invokes atdd validate coach with a marker expression
that excludes tests marked 'slow'.

RED state: The post-commit hook at src/atdd/coach/templates/hooks/post-commit does not
yet pass -m 'not slow' (or equivalent) to its atdd validate coach invocation. This test
fails because the slow-marker exclusion is absent.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOK_PATH = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "hooks" / "post-commit"


def test_post_commit_hook_excludes_slow_marked_tests():
    """AC-UNIT-001: post-commit hook must pass a 'not slow' marker exclusion to pytest."""
    hook_text = HOOK_PATH.read_text(encoding="utf-8")
    has_slow_exclusion = (
        "not slow" in hook_text
        or "--deselect" in hook_text
        or "slow" in hook_text
    )
    assert has_slow_exclusion, (
        f"Post-commit hook at {HOOK_PATH} does not exclude 'slow'-marked tests.\n"
        "Add '-m \"not slow\"' or equivalent marker expression to the atdd validate coach\n"
        "invocation so SMOKE tests that deliberately poison the live repo are not run\n"
        "by the post-commit hook (issue #845 Item A)."
    )
