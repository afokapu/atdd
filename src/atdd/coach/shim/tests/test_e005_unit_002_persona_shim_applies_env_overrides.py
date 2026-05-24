"""E005-UNIT-002 — PersonaShim.run() passes env_overrides to subprocess.Popen.

RED: fails until PersonaShim accepts env_overrides and merges into Popen env=.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

from atdd.coach.shim.persona_shim import PersonaShim


@pytest.mark.timeout(15)
def test_env_override_reaches_spawned_process(tmp_path):
    """Spawned process exits 0 if ATDD_AGENT_ID env var is set correctly."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    agent_dir = runtime_dir / "agents" / "e005-test-001"
    agent_dir.mkdir(parents=True)

    check_script = (
        "import os, sys; "
        "sys.exit(0 if os.environ.get('ATDD_AGENT_ID') == 'e005-test-001' else 1)"
    )

    shim = PersonaShim(
        agent_id="e005-test-001",
        spawn_command=[sys.executable, "-c", check_script],
        runtime_dir=runtime_dir,
        env_overrides={"ATDD_AGENT_ID": "e005-test-001"},
    )
    rc = shim.run()
    assert rc == 0, "Spawned process did not receive ATDD_AGENT_ID=e005-test-001"


@pytest.mark.timeout(15)
def test_env_overrides_merge_with_existing_env(tmp_path):
    """env_overrides are merged on top of os.environ — existing vars survive."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    agent_dir = runtime_dir / "agents" / "e005-merge-001"
    agent_dir.mkdir(parents=True)

    check_script = (
        "import os, sys; "
        "has_path = 'PATH' in os.environ; "
        "has_override = os.environ.get('ATDD_AGENT_ID') == 'e005-merge-001'; "
        "sys.exit(0 if (has_path and has_override) else 1)"
    )

    shim = PersonaShim(
        agent_id="e005-merge-001",
        spawn_command=[sys.executable, "-c", check_script],
        runtime_dir=runtime_dir,
        env_overrides={"ATDD_AGENT_ID": "e005-merge-001"},
    )
    rc = shim.run()
    assert rc == 0, "Merged env did not contain both PATH and the override"


@pytest.mark.timeout(15)
def test_empty_env_overrides_still_spawns(tmp_path):
    """PersonaShim with env_overrides={} still spawns the process normally."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    agent_dir = runtime_dir / "agents" / "e005-empty-001"
    agent_dir.mkdir(parents=True)

    shim = PersonaShim(
        agent_id="e005-empty-001",
        spawn_command=[sys.executable, "-c", "pass"],
        runtime_dir=runtime_dir,
        env_overrides={},
    )
    rc = shim.run()
    assert rc == 0
