# URN: test:spawn-agents:E019-INTEGRATION-001-path-bleed-regression
# Acceptance: acc:spawn-agents:E019-INTEGRATION-001-path-bleed-regression
# WMBT: wmbt:spawn-agents:E019
# Phase: GREEN
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E019-INTEGRATION-001 — regression: when the caller supplies a relative runtime_root
and the process CWD changes between construction and shim exec (simulating the worktree
cd), the shim writes output.log at the pre-resolved absolute path.

_verify_process_alive polled at the absolute path finds the heartbeat byte and does
not raise ProcessNotAlive.  No output.log appears at the CWD-bled path.

RED: fails until _build_shim_command resolves runtime_root to absolute so the --runtime-dir
passed to the fake shim refers to the original (pre-CWD-change) location.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_path_bleed_regression_output_log_at_absolute_not_bled_path(tmp_path, monkeypatch):
    from atdd.coach.commands.spawn import _build_shim_command, _verify_process_alive

    # ── Setup ───────────────────────────────────────────────────────────────
    agent_id = "integration-860-bleed"

    # The runtime_root the caller supplies — relative (the CWD-bleed scenario).
    relative_suffix = "out/runtime"

    # Absolute pre-CWD-change root (what the resolved path should be).
    original_cwd = tmp_path / "original_cwd"
    original_cwd.mkdir()
    expected_abs_runtime = original_cwd / relative_suffix

    # A different directory that simulates the worktree CWD after the cd.
    worktree_cwd = tmp_path / "worktree_dir"
    worktree_cwd.mkdir()

    # Work with the original CWD first so relative_suffix resolves to expected_abs_runtime.
    monkeypatch.chdir(original_cwd)

    runtime_root_rel = Path(relative_suffix)
    assert not runtime_root_rel.is_absolute(), "precondition: input is relative"

    # Build the shim command while CWD == original_cwd.
    cmd = _build_shim_command("echo ok", agent_id, runtime_root_rel)

    # Extract --runtime-dir value from the built command.
    import shlex
    tokens = shlex.split(cmd)
    idx = tokens.index("--runtime-dir")
    runtime_dir_in_cmd = tokens[idx + 1]

    # ── Simulate CWD change (the worktree cd) ───────────────────────────────
    monkeypatch.chdir(worktree_cwd)

    # The fake shim: writes one byte to agents/<id>/output.log at the path it received.
    agent_out_dir = Path(runtime_dir_in_cmd) / "agents" / agent_id
    agent_out_dir.mkdir(parents=True, exist_ok=True)
    output_log_at_received = agent_out_dir / "output.log"
    output_log_at_received.write_bytes(b"shim heartbeat\n")

    # ── Assertions ──────────────────────────────────────────────────────────
    # 1. The received --runtime-dir is absolute (no relative bleed possible).
    assert Path(runtime_dir_in_cmd).is_absolute(), (
        f"E019-INTEGRATION-001: --runtime-dir must be absolute. Got: {runtime_dir_in_cmd!r}"
    )

    # 2. output.log exists at the resolved absolute path (not the CWD-bled path).
    abs_agent_dir = expected_abs_runtime / "agents" / agent_id
    abs_output_log = abs_agent_dir / "output.log"
    assert abs_output_log.exists(), (
        f"E019-INTEGRATION-001: output.log must exist at the pre-resolved absolute path "
        f"{abs_output_log}. This fails when _build_shim_command does not call .resolve() "
        "and the CWD changes before shim exec."
    )

    # 3. No output.log at the CWD-bled location.
    bled_output_log = worktree_cwd / relative_suffix / "agents" / agent_id / "output.log"
    assert not bled_output_log.exists(), (
        f"E019-INTEGRATION-001: output.log must NOT exist at CWD-bled path {bled_output_log}."
    )

    # 4. _verify_process_alive does not raise when polled at the absolute location.
    class _AliveProc:
        def poll(self):
            return None

    _verify_process_alive(
        proc=_AliveProc(),
        agent_id=agent_id,
        runtime_dir=abs_agent_dir,
        transport="cli-return",
        timeout_s=0.5,
    )
    # Must not raise — heartbeat byte is visible at the absolute polled path.
