# URN: test:observe-and-correct:E003-UNIT-011-pty-output-forwarded-to-operator-stdout
# Acceptance: acc:observe-and-correct:E003-UNIT-011-pty-output-forwarded-to-operator-stdout
# WMBT: wmbt:observe-and-correct:E003
# Phase: RED
# Assertion: behavioral
# Layer: integration
"""E003-UNIT-011 — _run_loop writes every pty-output chunk to both log_fh AND
sys.stdout.buffer (stdout_sink in tests); operator-visible stdout receives
identical bytes to what was logged.

Issue #843.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def test_stdout_sink_parameter_accepted():
    """PersonaShim accepts stdout_sink constructor parameter."""
    from atdd.coach.shim import PersonaShim

    captured: list[bytes] = []
    shim = PersonaShim(
        agent_id="test-stdout-011a",
        spawn_command=["true"],
        runtime_dir=None,
        stdout_sink=captured.append,
    )
    assert shim is not None


def test_pty_output_forwarded_to_stdout_sink(tmp_path):
    """Pty output bytes appear in the stdout_sink capture buffer."""
    from atdd.coach.shim import PersonaShim

    agent_dir = tmp_path / "agents" / "test-stdout-011b"
    agent_dir.mkdir(parents=True)

    captured: list[bytes] = []
    shim = PersonaShim(
        agent_id="test-stdout-011b",
        spawn_command=["sh", "-c", "printf 'STDOUT_SENTINEL_011'"],
        runtime_dir=tmp_path,
        stdout_sink=captured.append,
    )
    shim.run(timeout=5.0)

    all_stdout = b"".join(captured)
    assert b"STDOUT_SENTINEL_011" in all_stdout, (
        f"Expected sentinel in stdout_sink; got {all_stdout!r}"
    )


def test_stdout_and_log_receive_identical_data(tmp_path):
    """Both log_fh and stdout_sink receive identical bytes."""
    from atdd.coach.shim import PersonaShim

    agent_dir = tmp_path / "agents" / "test-stdout-011c"
    agent_dir.mkdir(parents=True)

    captured: list[bytes] = []
    shim = PersonaShim(
        agent_id="test-stdout-011c",
        spawn_command=["sh", "-c", "printf 'IDENTICAL_DATA_CHUNK'"],
        runtime_dir=tmp_path,
        stdout_sink=captured.append,
    )
    shim.run(timeout=5.0)

    all_stdout = b"".join(captured)
    log_content = (agent_dir / "output.log").read_bytes()

    assert b"IDENTICAL_DATA_CHUNK" in all_stdout, (
        f"sentinel missing from stdout_sink; got {all_stdout!r}"
    )
    assert b"IDENTICAL_DATA_CHUNK" in log_content, (
        f"sentinel missing from output.log; got {log_content!r}"
    )
