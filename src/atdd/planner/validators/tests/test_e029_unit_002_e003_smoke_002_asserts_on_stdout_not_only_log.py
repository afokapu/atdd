# URN: test:govern-lifecycle:smoke-false-green-prevention:E029-UNIT-002-e003-smoke-002-asserts-on-stdout-not-only-log
# Acceptance: acc:govern-lifecycle:E029-UNIT-002-e003-smoke-002-asserts-on-stdout-not-only-log
# WMBT: wmbt:govern-lifecycle:E029
# Phase: RED
# Layer: unit
# Assertion: structural
"""
RED: test_e003_smoke_002_operator_stdout_visible.py must assert on captured
stdout, not solely on output.log, AND must not embed a _SYNTHETIC_AGENT script
(the entry point must be the real atdd spawn path).  Currently fails on the
_SYNTHETIC_AGENT check because the file embeds a synthetic agent script.
"""
from __future__ import annotations

import pytest
from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.planner]

_TARGET = (
    find_repo_root()
    / "src"
    / "atdd"
    / "coach"
    / "shim"
    / "tests"
    / "test_e003_smoke_002_operator_stdout_visible.py"
)

_STDOUT_CAPTURE_PATTERNS = ["proc.stdout", "captured_output", "stdout_data", "all_stdout"]


def test_e003_smoke_002_asserts_on_stdout_stream():
    """test_e003_smoke_002 must contain a stdout-capture assertion, not just output.log reads."""
    assert _TARGET.exists(), f"Target test file not found: {_TARGET}"
    content = _TARGET.read_text()
    has_stdout_assertion = any(pat in content for pat in _STDOUT_CAPTURE_PATTERNS)
    assert has_stdout_assertion, (
        f"test_e003_smoke_002 is missing a stdout-stream assertion "
        f"({', '.join(_STDOUT_CAPTURE_PATTERNS)}). "
        "SMOKE tests must assert on operator-observable behavior (captured stdout), "
        "not only on output.log file content."
    )


def test_e003_smoke_002_has_no_synthetic_agent_script():
    """test_e003_smoke_002 must not embed a _SYNTHETIC_AGENT script — use real atdd spawn."""
    assert _TARGET.exists(), f"Target test file not found: {_TARGET}"
    content = _TARGET.read_text()
    assert "_SYNTHETIC_AGENT" not in content, (
        "test_e003_smoke_002 embeds a _SYNTHETIC_AGENT synthetic script. "
        "The retrofit must use a real atdd spawn invocation so that the full "
        "production wiring (PersonaShim via cmd_spawn) is exercised."
    )
