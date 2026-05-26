# URN: test:observe-and-correct:E007-UNIT-002-sentinel-configurable-per-adapter
# Acceptance: acc:observe-and-correct:E007-UNIT-002-sentinel-configurable-per-adapter
# WMBT: wmbt:observe-and-correct:E007
# Phase: RED
# Assertion: behavioral
# Layer: application
"""E007-UNIT-002 — The submit sentinel is configurable: PersonaShim(submit_sentinel=b'\\n')
uses LF; ATDD_SHIM_SUBMIT_SENTINEL env var overrides; PersonaShim(submit_sentinel=b'')
disables sentinel appending entirely.

Issue #862.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _append_cli_return(path: Path, correction_text: str) -> None:
    record = {
        "rule_id": "TEST-E007-002",
        "correction_text": correction_text,
        "severity": 3,
        "issued_at": "2026-05-26T00:00:00Z",
    }
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def _make_shim(tmp_path: Path, agent_id: str, captured: list[bytes], **kwargs):
    from atdd.coach.shim import PersonaShim

    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    cli_return_path = agent_dir / "cli-return.jsonl"
    _append_cli_return(cli_return_path, "test")

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "60"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: captured.append(data),
        **kwargs,
    )
    return shim


def test_lf_sentinel_via_constructor(tmp_path):
    """submit_sentinel=b'\\n' makes the sink receive b'test\\n'.

    RED: TypeError — submit_sentinel not accepted by PersonaShim.__init__.
    """
    captured: list[bytes] = []
    shim = _make_shim(tmp_path, "e007-unit-002-lf", captured, submit_sentinel=b"\n")
    shim.poll_once()
    assert captured == [b"test\n"], (
        f"Expected [b'test\\n'] but got {captured!r}"
    )


def test_lf_sentinel_via_env_var(tmp_path, monkeypatch):
    """ATDD_SHIM_SUBMIT_SENTINEL='\\n' env var overrides and makes the sink
    receive b'test\\n'.

    RED: env var is not read — sink receives b'test' (no sentinel at all
    since the feature doesn't exist yet) — assertion fails.
    """
    monkeypatch.setenv("ATDD_SHIM_SUBMIT_SENTINEL", "\n")

    captured: list[bytes] = []
    # No submit_sentinel kwarg — sentinel must come from env var.
    shim = _make_shim(tmp_path, "e007-unit-002-env", captured)
    shim.poll_once()
    assert captured == [b"test\n"], (
        f"ATDD_SHIM_SUBMIT_SENTINEL='\\n' must override sentinel; got {captured!r}"
    )


def test_empty_sentinel_disables_appending(tmp_path):
    """submit_sentinel=b'' disables sentinel appending; sink receives bare bytes.

    RED: TypeError — submit_sentinel not accepted by PersonaShim.__init__.
    """
    captured: list[bytes] = []
    shim = _make_shim(tmp_path, "e007-unit-002-empty", captured, submit_sentinel=b"")
    shim.poll_once()
    assert captured == [b"test"], (
        f"submit_sentinel=b'' must disable appending; got {captured!r}"
    )


def test_constructor_sentinel_overrides_env_var(tmp_path, monkeypatch):
    """When both submit_sentinel kwarg and ATDD_SHIM_SUBMIT_SENTINEL are set,
    the constructor argument takes precedence.

    RED: TypeError — submit_sentinel not accepted.
    """
    monkeypatch.setenv("ATDD_SHIM_SUBMIT_SENTINEL", "\n")

    captured: list[bytes] = []
    # Explicit b'\r' must win over the '\\n' env var.
    shim = _make_shim(tmp_path, "e007-unit-002-override", captured, submit_sentinel=b"\r")
    shim.poll_once()
    assert captured == [b"test\r"], (
        f"Constructor submit_sentinel must override env var; got {captured!r}"
    )
