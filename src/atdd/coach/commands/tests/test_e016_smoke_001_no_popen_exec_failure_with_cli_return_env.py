"""E016-SMOKE-001 — installed atdd-shim with --env flag exits 0, no FileNotFoundError.

Smoke test: invokes the real atdd-shim CLI (via subprocess) with --env ATDD_AGENT_ID=...
wrapping python3 -c 'pass'. Asserts no FileNotFoundError and exit code 0.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke


@pytest.mark.timeout(20)
def test_shim_with_env_flag_exits_zero(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    agent_dir = runtime_dir / "agents" / "smoke-e016-001"
    agent_dir.mkdir(parents=True)

    result = subprocess.run(
        [
            "atdd-shim",
            "--agent-id", "smoke-e016-001",
            "--runtime-dir", str(runtime_dir),
            "--env", "ATDD_AGENT_ID=smoke-e016-001",
            "--",
            sys.executable, "-c", "pass",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert "No such file or directory" not in result.stderr, (
        f"FileNotFoundError in stderr:\n{result.stderr}"
    )
    assert result.returncode == 0, (
        f"atdd-shim exited {result.returncode}\nstderr: {result.stderr}"
    )
