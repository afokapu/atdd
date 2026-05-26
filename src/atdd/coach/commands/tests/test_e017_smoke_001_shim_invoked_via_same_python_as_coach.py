# URN: test:spawn-agents:shim-path-resolution-bug:E017-SMOKE-001-shim-invoked-via-same-python-as-coach
# Acceptance: acc:spawn-agents:E017-SMOKE-001-shim-invoked-via-same-python-as-coach
# WMBT: wmbt:spawn-agents:E017
# Phase: SMOKE
# Layer: backend.smoke
# Runtime: python
# Assertion: behavioral
"""E017-SMOKE-001 — the spawned shim command uses the same Python interpreter as
the running coach process (sys.executable), not a PATH-resolved 'atdd-shim' binary.

Smoke gate: only runs when ATDD_RUN_SMOKE=1 is set.
"""
from __future__ import annotations

import os
import sys

import pytest

pytestmark = [pytest.mark.smoke]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="E017-SMOKE-001 requires ATDD_RUN_SMOKE=1",
)
def test_shim_command_first_token_matches_sys_executable():
    """_build_shim_command first token must equal sys.executable — no PATH resolution."""
    from atdd.coach.commands.spawn import _build_shim_command

    cmd = _build_shim_command(
        agent_id="smoke-e017-001",
        runtime_root=None,
        env_overrides={},
        adapter_command="echo hello",
    )
    words = cmd.split()
    assert words[0] == sys.executable, (
        f"E017-SMOKE-001: shim command first token must be sys.executable={sys.executable!r}. "
        f"Got: {words[0]!r}. Full command: {cmd!r}"
    )
    assert words[1] == "-m", (
        f"E017-SMOKE-001: second token must be '-m'. Got: {words[1]!r}. Full: {cmd!r}"
    )
    assert words[2] == "atdd.coach.shim", (
        f"E017-SMOKE-001: third token must be 'atdd.coach.shim'. Got: {words[2]!r}. Full: {cmd!r}"
    )
