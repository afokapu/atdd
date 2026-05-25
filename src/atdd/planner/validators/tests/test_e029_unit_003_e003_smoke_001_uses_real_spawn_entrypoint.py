# URN: test:govern-lifecycle:smoke-false-green-prevention:E029-UNIT-003-e003-smoke-001-uses-real-spawn-entrypoint
# Acceptance: acc:govern-lifecycle:E029-UNIT-003-e003-smoke-001-uses-real-spawn-entrypoint
# WMBT: wmbt:govern-lifecycle:E029
# Phase: RED
# Layer: unit
# Assertion: structural
"""
RED: test_e003_smoke_001_correction_loop_end_to_end.py must invoke atdd spawn
as a real subprocess — not a hand-rolled Popen of a synthetic command.
Currently fails because the file does not contain an 'atdd spawn' invocation
(it instantiates PersonaShim directly with a synthetic agent script).
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
    / "test_e003_smoke_001_correction_loop_end_to_end.py"
)


def test_e003_smoke_001_uses_real_spawn_entrypoint():
    """test_e003_smoke_001 must contain an atdd spawn subprocess invocation."""
    assert _TARGET.exists(), f"Target test file not found: {_TARGET}"
    content = _TARGET.read_text()
    has_real_spawn = (
        ("atdd" in content and "spawn" in content)
        or "invoke_atdd_spawn" in content
    )
    assert has_real_spawn, (
        "test_e003_smoke_001 does not invoke 'atdd spawn'. "
        "The retrofit must launch the real CLI entry point (atdd spawn) as a subprocess "
        "so that _inject_agent_env, PersonaShim, and the full command-construction path "
        "are exercised — not a hand-rolled Popen of a synthetic agent script."
    )


def test_e003_smoke_001_has_no_synthetic_cat_or_sleep_popen():
    """test_e003_smoke_001 must not use Popen(['cat',...]) or Popen(['sleep',...]) stubs."""
    assert _TARGET.exists(), f"Target test file not found: {_TARGET}"
    content = _TARGET.read_text()
    for stub in ("['cat'", "['sleep'", '["cat"', '["sleep"'):
        assert stub not in content, (
            f"test_e003_smoke_001 contains a stub Popen command: {stub!r}. "
            "Remove synthetic subprocess stubs and drive the real atdd spawn entry point."
        )
