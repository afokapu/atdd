# URN: test:observe-and-correct:E003-SMOKE-002-operator-stdout-visible
# Acceptance: acc:observe-and-correct:E003-SMOKE-002-operator-stdout-visible
# WMBT: wmbt:observe-and-correct:E003
# Phase: SMOKE
# Assertion: behavioral
# Layer: integration
"""E003-SMOKE-002 — Operator-stdout visibility: atdd-shim forwards pty output
to its own stdout so the operator's cmux pane renders the agent TUI.

Launches atdd-shim as a subprocess (the real CLI entry point, ``python -m
atdd.coach.shim``) with stdout=PIPE, wrapping a sentinel-writing agent script
written to tmp_path. Asserts the sentinel appears in the captured shim stdout
within 10 seconds.

Does NOT use stdout_sink — exercises the real sys.stdout.buffer.write path.

Issue #843. Retrofit by #855 (remove embedded synthetic-agent string constant).
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.platform]

# Resolve worktree src root so the subprocess uses the local persona_shim.py
# rather than the pipx-installed copy. pytest adds this via pythonpath=[src]
# but subprocesses need it explicitly.
_SRC_ROOT = str(Path(__file__).parent.parent.parent.parent.parent)  # …/src

<<<<<<< HEAD
_AGENT_SCRIPT = """\
=======
_STDOUT_SENTINEL_AGENT = """\
>>>>>>> origin/main
import sys, time
sys.stdout.write("STDOUT_SENTINEL_E003_SMOKE_002\\n")
sys.stdout.flush()
time.sleep(0.2)
"""


def test_shim_stdout_carries_pty_output(tmp_path):
    """atdd-shim stdout contains pty output from the wrapped subprocess."""
    agent_dir = tmp_path / "agents" / "smoke-002"
    agent_dir.mkdir(parents=True)

<<<<<<< HEAD
    agent_script = tmp_path / "agent_script_smoke002.py"
    agent_script.write_text(_AGENT_SCRIPT)
=======
    agent_script = tmp_path / "stdout_sentinel_agent.py"
    agent_script.write_text(_STDOUT_SENTINEL_AGENT)
>>>>>>> origin/main

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{_SRC_ROOT}:{existing_pythonpath}" if existing_pythonpath else _SRC_ROOT

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "atdd.coach.shim",
            "--agent-id", "smoke-002",
            "--runtime-dir", str(tmp_path),
            "--",
            sys.executable, str(agent_script),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    collected: list[bytes] = []
    deadline = time.monotonic() + 10.0

    def _reader() -> None:
        assert proc.stdout is not None
        for chunk in iter(lambda: proc.stdout.read(256), b""):
            collected.append(chunk)

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()

    # Wait for process to finish or sentinel to appear
    while time.monotonic() < deadline:
        combined = b"".join(collected)
        if b"STDOUT_SENTINEL_E003_SMOKE_002" in combined:
            break
        if proc.poll() is not None:
            break
        time.sleep(0.1)

    proc.wait(timeout=5.0)
    reader.join(timeout=2.0)

    all_stdout = b"".join(collected)
    assert b"STDOUT_SENTINEL_E003_SMOKE_002" in all_stdout, (
        "Shim stdout did not contain the sentinel — pty output not forwarded to "
        f"operator-visible stdout.\nstdout={all_stdout!r}\n"
        f"stderr={proc.stderr.read()!r}"  # type: ignore[union-attr]
    )
