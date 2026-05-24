"""E005-UNIT-003 — regression: PersonaShim with argv-leading KEY=value fails.

Documents the pre-fix behavior: Popen exec treats 'ATDD_AGENT_ID=x' as a
binary path and raises FileNotFoundError. The fix prevents this argv shape
from being produced by _build_shim_command (E016), but this test proves the
underlying Popen behavior and confirms we understand the root cause.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from atdd.coach.shim.persona_shim import PersonaShim


@pytest.mark.timeout(10)
def test_shell_prefix_in_argv_causes_file_not_found(tmp_path):
    """Popen with argv-leading KEY=value raises FileNotFoundError (confirms bug)."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    agent_dir = runtime_dir / "agents" / "broken-001"
    agent_dir.mkdir(parents=True)

    shim = PersonaShim(
        agent_id="broken-001",
        spawn_command=["ATDD_AGENT_ID=broken-001", sys.executable, "-c", "pass"],
        runtime_dir=runtime_dir,
        env_overrides={},
    )
    with pytest.raises(FileNotFoundError):
        shim.run()
