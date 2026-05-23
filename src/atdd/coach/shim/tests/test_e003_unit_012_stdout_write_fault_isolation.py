# URN: test:observe-and-correct:E003-UNIT-012-stdout-write-fault-isolation
# Acceptance: acc:observe-and-correct:E003-UNIT-012-stdout-write-fault-isolation
# WMBT: wmbt:observe-and-correct:E003
# Phase: RED
# Assertion: behavioral
# Layer: integration
"""E003-UNIT-012 — When writing to stdout raises OSError, _run_loop logs the
error with extra= and continues; it does not crash or stop serving log_fh and
cli-return.

Issue #843.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


class _RaisingOnFirst:
    """Sink that raises OSError on the first call; succeeds on subsequent calls."""

    def __init__(self) -> None:
        self._calls: int = 0
        self.received: list[bytes] = []

    def __call__(self, data: bytes) -> None:
        self._calls += 1
        if self._calls == 1:
            raise OSError("simulated stdout write failure")
        self.received.append(data)


def test_shim_survives_stdout_write_error(tmp_path):
    """Shim does not crash when stdout_sink raises OSError on first chunk."""
    from atdd.coach.shim import PersonaShim

    agent_dir = tmp_path / "agents" / "test-fault-012a"
    agent_dir.mkdir(parents=True)

    raising_sink = _RaisingOnFirst()
    shim = PersonaShim(
        agent_id="test-fault-012a",
        spawn_command=["sh", "-c", "printf 'chunk1'; printf 'chunk2'"],
        runtime_dir=tmp_path,
        stdout_sink=raising_sink,
    )
    # Must not raise
    exit_code = shim.run(timeout=5.0)
    assert exit_code == 0, f"Shim crashed with exit code {exit_code}"


def test_log_fh_still_receives_data_after_stdout_error(tmp_path):
    """log_fh still receives output chunks even when stdout_sink raises."""
    from atdd.coach.shim import PersonaShim

    agent_dir = tmp_path / "agents" / "test-fault-012b"
    agent_dir.mkdir(parents=True)

    raising_sink = _RaisingOnFirst()
    shim = PersonaShim(
        agent_id="test-fault-012b",
        spawn_command=["sh", "-c", "printf 'LOG_MUST_SURVIVE_012'"],
        runtime_dir=tmp_path,
        stdout_sink=raising_sink,
    )
    shim.run(timeout=5.0)

    log_content = (agent_dir / "output.log").read_bytes()
    assert b"LOG_MUST_SURVIVE_012" in log_content, (
        f"log_fh did not receive data after stdout error; got {log_content!r}"
    )
