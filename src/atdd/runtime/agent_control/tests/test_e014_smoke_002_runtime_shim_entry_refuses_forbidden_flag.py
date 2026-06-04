# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E014-SMOKE-002-runtime-shim-entry-refuses-forbidden-flag-smoke
# Acceptance: acc:govern-lifecycle:E014-SMOKE-002-runtime-shim-entry-refuses-forbidden-flag
# WMBT: wmbt:govern-lifecycle:E014
# Phase: SMOKE
# Layer: assembly
# Smoke: true
# Assertion: behavioral
# Purpose: The real runtime shim CLI (`python -m atdd.runtime.agent_control`) refuses a
#          forbidden-flag launch command at the process-spawn boundary — operator sees a
#          non-zero exit + a stderr message naming the flag, and no agent process starts.
"""acc:govern-lifecycle:E014-SMOKE-002 — runtime shim CLI entry refuses the forbidden flag.

Real entry point: spawns the actual `python -m atdd.runtime.agent_control` module CLI as
a subprocess (the same shim entry the cli-return dispatch invokes) — driving production
wiring directly, not a substituted surface or in-process double. Operator-observable
assertions: non-zero exit code + stderr naming the forbidden flag + NO agent runtime
directory created (the launch was refused before any process spawned).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _src_root() -> Path:
    # .../src/atdd/runtime/agent_control/tests/<this file> → ascend to the src/ dir.
    return Path(__file__).resolve().parents[5]


def test_runtime_shim_entry_refuses_forbidden_flag(tmp_path):
    src_root = _src_root()
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(src_root), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "atdd.runtime.agent_control",
            "--agent-id",
            "e014-smoke-002",
            "--runtime-dir",
            str(tmp_path),
            "--",
            "claude",
            "--dangerously-skip-permissions",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert proc.returncode != 0, (
        f"shim CLI must exit non-zero on the forbidden flag; "
        f"rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "--dangerously-skip-permissions" in proc.stderr, proc.stderr
    # Operator-observable: no agent process was launched (no runtime artifacts).
    assert not (tmp_path / "agents" / "e014-smoke-002").exists(), (
        "a forbidden-flag launch must be refused before any agent process starts"
    )
