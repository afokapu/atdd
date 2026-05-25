# URN: test:govern-lifecycle:smoke-false-green-prevention:E029-UNIT-001-e003-smoke-001-has-no-fakemultiplexer
# Acceptance: acc:govern-lifecycle:E029-UNIT-001-e003-smoke-001-has-no-fakemultiplexer
# WMBT: wmbt:govern-lifecycle:E029
# Phase: RED
# Layer: unit
# Assertion: structural
"""
RED: test_e003_smoke_001_correction_loop_end_to_end.py must not import or
instantiate FakeMultiplexer, and must not directly instantiate PersonaShim
(the real entry point must flow through atdd spawn).  Currently fails on the
PersonaShim( check because the file directly instantiates PersonaShim rather
than delegating to atdd spawn.
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


def test_e003_smoke_001_has_no_fakemultiplexer():
    """test_e003_smoke_001 must not import or instantiate FakeMultiplexer."""
    assert _TARGET.exists(), f"Target test file not found: {_TARGET}"
    content = _TARGET.read_text()
    assert "FakeMultiplexer" not in content, (
        "test_e003_smoke_001 contains 'FakeMultiplexer'. "
        "The file must not import or instantiate FakeMultiplexer — "
        "use the real atdd spawn entry point instead."
    )


def test_e003_smoke_001_has_no_direct_persona_shim_instantiation():
    """test_e003_smoke_001 must not directly instantiate PersonaShim (bypasses spawn wiring)."""
    assert _TARGET.exists(), f"Target test file not found: {_TARGET}"
    content = _TARGET.read_text()
    assert "PersonaShim(" not in content, (
        "test_e003_smoke_001 directly instantiates PersonaShim(). "
        "The retrofit must route through 'atdd spawn' so that _inject_agent_env "
        "and the full command-construction path are exercised."
    )
