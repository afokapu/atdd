# URN: test:govern-lifecycle:close-substrate-friction-regressions:E022-UNIT-002-smoke-test-has-slow-marker
# Acceptance: acc:govern-lifecycle:E022-UNIT-002-smoke-test-has-slow-marker
# WMBT: wmbt:govern-lifecycle:E022
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-002: test_guard_catches_real_live_repo_contamination is marked with
pytest.mark.slow so marker-based exclusion in the post-commit hook works.

RED state: The test at src/atdd/coach/validators/test_y003_smoke_001_guard_catches_polluter.py
does not yet carry pytest.mark.slow on test_guard_catches_real_live_repo_contamination.
This test fails because the marker is absent.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

REPO_ROOT = Path(__file__).resolve().parents[6]
SMOKE_TEST_PATH = (
    REPO_ROOT
    / "src"
    / "atdd"
    / "coach"
    / "validators"
    / "test_y003_smoke_001_guard_catches_polluter.py"
)
TARGET_TEST = "test_guard_catches_real_live_repo_contamination"


def test_live_repo_contamination_test_has_slow_mark():
    """AC-UNIT-002: test_guard_catches_real_live_repo_contamination must carry pytest.mark.slow."""
    source = SMOKE_TEST_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == TARGET_TEST:
            decorators = [ast.unparse(d) for d in node.decorator_list]
            marks_in_source = [d for d in decorators if "slow" in d]
            pytestmark_slow = "slow" in source and "pytestmark" in source
            has_mark = bool(marks_in_source) or pytestmark_slow
            assert has_mark, (
                f"{TARGET_TEST} in {SMOKE_TEST_PATH} does not have pytest.mark.slow.\n"
                "Add @pytest.mark.slow or include 'slow' in the pytestmark list so the\n"
                "post-commit hook's '-m not slow' exclusion filters this test out\n"
                "(issue #845 Item A — this test deliberately sets core.bare=true on the live repo)."
            )
            return

    pytest.fail(
        f"Function '{TARGET_TEST}' not found in {SMOKE_TEST_PATH}.\n"
        "Either the file was moved or the function was renamed."
    )
