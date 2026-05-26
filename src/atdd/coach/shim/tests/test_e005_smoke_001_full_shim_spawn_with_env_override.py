# URN: test:observe-and-correct:E005-SMOKE-001-full-shim-spawn-with-env-override
# Acceptance: acc:observe-and-correct:E005-SMOKE-001-full-shim-spawn-with-env-override
# WMBT: wmbt:observe-and-correct:E005
# Phase: SMOKE
# Assertion: integration
"""E005-SMOKE-001 — atdd-shim with --env delivers env var to spawned process stdout.

End-to-end: the synthetic adapter prints $ATDD_AGENT_ID; captured shim stdout
must contain the sentinel value, proving the env var reached the pty.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke


@pytest.mark.timeout(20)
def test_env_var_reaches_spawned_process_stdout(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    agent_dir = runtime_dir / "agents" / "smoke-e005-001"
    agent_dir.mkdir(parents=True)

    agent_script = tmp_path / "agent.py"
    agent_script.write_text(
        textwrap.dedent("""\
        import os, sys
        sentinel = os.environ.get("ATDD_AGENT_ID", "MISSING")
        sys.stdout.write(sentinel + "\\n")
        sys.stdout.flush()
        """)
    )

    result = subprocess.run(
        [
            "atdd-shim",
            "--agent-id", "smoke-e005-001",
            "--runtime-dir", str(runtime_dir),
            "--env", "ATDD_AGENT_ID=smoke-e005-001",
            "--",
            sys.executable, str(agent_script),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )

    combined_out = result.stdout + (agent_dir / "output.log").read_text(errors="replace") if (agent_dir / "output.log").exists() else result.stdout
    assert "smoke-e005-001" in combined_out, (
        f"Sentinel 'smoke-e005-001' not found in output.\n"
        f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )
    assert result.returncode == 0, (
        f"atdd-shim exited {result.returncode}\nstderr: {result.stderr}"
    )
