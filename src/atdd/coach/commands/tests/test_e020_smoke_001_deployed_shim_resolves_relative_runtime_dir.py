# URN: test:spawn-agents:E020-SMOKE-001-deployed-shim-resolves-relative-runtime-dir
# Acceptance: acc:spawn-agents:E020-SMOKE-001-deployed-shim-resolves-relative-runtime-dir
# WMBT: wmbt:spawn-agents:E020
# Phase: SMOKE
# Layer: backend.smoke
# Runtime: python
# Assertion: behavioral
"""E020-SMOKE-001 — the deployed atdd.coach.shim.__main__ module resolves
--runtime-dir to absolute before handing it to PersonaShim; confirmed against
the live installed package.

Smoke gate: requires ATDD_RUN_SMOKE=1.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.smoke]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="E020-SMOKE-001 requires ATDD_RUN_SMOKE=1",
)
def test_deployed_shim_main_resolves_relative_runtime_dir(tmp_path, monkeypatch):
    from atdd.coach.shim.__main__ import main

    captured: list[Path] = []

    class _CapturingShim:
        def __init__(self, agent_id, spawn_command, runtime_dir, env_overrides=None):
            captured.append(runtime_dir)

        def run(self):
            return 0

    monkeypatch.chdir(tmp_path)

    with patch("atdd.coach.shim.persona_shim.PersonaShim", _CapturingShim):
        main([
            "--agent-id", "smoke-x-e020",
            "--runtime-dir", ".atdd/runtime",
            "--", "echo", "ok",
        ])

    assert captured, "E020-SMOKE-001: PersonaShim was never instantiated"
    received = captured[0]
    assert received.is_absolute(), (
        f"E020-SMOKE-001: deployed shim main() must resolve relative --runtime-dir to absolute. "
        f"Got: {received!r}"
    )


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="E020-SMOKE-001 requires ATDD_RUN_SMOKE=1",
)
def test_deployed_shim_main_absolute_runtime_dir_unchanged():
    from atdd.coach.shim.__main__ import main

    captured: list[Path] = []

    class _CapturingShim:
        def __init__(self, agent_id, spawn_command, runtime_dir, env_overrides=None):
            captured.append(runtime_dir)

        def run(self):
            return 0

    with patch("atdd.coach.shim.persona_shim.PersonaShim", _CapturingShim):
        main([
            "--agent-id", "smoke-x-e020-abs",
            "--runtime-dir", "/tmp/smoke-e020-abs",
            "--", "echo", "ok",
        ])

    assert captured
    received = captured[0]
    assert received.is_absolute(), (
        f"E020-SMOKE-001: absolute --runtime-dir must remain absolute. Got: {received!r}"
    )
