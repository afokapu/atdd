# URN: test:observe-and-correct:E003-UNIT-001-shim-spawns-agent-in-pty
# Acceptance: acc:observe-and-correct:E003-UNIT-001-shim-spawns-agent-in-pty
# WMBT: wmbt:observe-and-correct:E003
# Phase: RED
# Assertion: behavioral
# Layer: integration
"""E003-UNIT-001 — The persona-shim spawns the agent CLI as a child process
inside a pty it owns; output flows through the pty master fd to output.log.

Issue #824.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def test_persona_shim_module_exists():
    """PersonaShim class is importable from atdd.coach.shim."""
    from atdd.coach.shim import PersonaShim  # noqa: F401  # RED: module doesn't exist yet


def test_persona_shim_accepts_agent_id_and_spawn_command(tmp_path):
    """PersonaShim can be constructed with agent_id and spawn_command."""
    from atdd.coach.shim import PersonaShim

    shim = PersonaShim(
        agent_id="test-agent-001",
        spawn_command=["echo", "hello"],
        runtime_dir=tmp_path,
    )
    assert shim.agent_id == "test-agent-001"


def test_persona_shim_spawns_child_in_pty(tmp_path):
    """When started, the shim spawns the agent CLI in a pty it owns.

    Uses 'true' as the agent command — it exits immediately, allowing
    the test to assert the shim completed without hanging.
    """
    from atdd.coach.shim import PersonaShim

    shim = PersonaShim(
        agent_id="test-agent-pty",
        spawn_command=["true"],
        runtime_dir=tmp_path,
    )
    exit_code = shim.run(timeout=5.0)
    assert exit_code == 0, f"Expected exit 0, got {exit_code}"


def test_persona_shim_tees_output_to_log(tmp_path):
    """Pty output is written to agents/<id>/output.log."""
    from atdd.coach.shim import PersonaShim

    agent_dir = tmp_path / "agents" / "test-agent-tee"
    agent_dir.mkdir(parents=True)

    shim = PersonaShim(
        agent_id="test-agent-tee",
        spawn_command=["sh", "-c", "echo 'hello from agent'"],
        runtime_dir=tmp_path,
    )
    shim.run(timeout=5.0)

    output_log = agent_dir / "output.log"
    assert output_log.exists(), "output.log was not created"
    content = output_log.read_text()
    assert "hello from agent" in content, f"Expected 'hello from agent' in output.log, got: {content!r}"
