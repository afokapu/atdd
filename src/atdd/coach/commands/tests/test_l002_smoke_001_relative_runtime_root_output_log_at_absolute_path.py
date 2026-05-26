# URN: test:spawn-agents:L002-SMOKE-001-relative-runtime-root-output-log-at-absolute-path
# Acceptance: acc:spawn-agents:L002-SMOKE-001-relative-runtime-root-output-log-at-absolute-path
# WMBT: wmbt:spawn-agents:L002
# Phase: SMOKE
# Layer: backend.smoke
# Runtime: python
# Assertion: behavioral
"""L002-SMOKE-001 — end-to-end regression gate: with runtime_root supplied as a
relative path, the shim writes output.log at the resolved absolute path and no
output.log appears at any CWD-bled worktree-relative location.
_verify_process_alive does not raise ProcessNotAlive.

This SMOKE test is the definitive regression gate: any future change that
reintroduces relative-path bleed will cause _verify_process_alive to raise here
before it causes a false-crash in production.

Reproduces the exact setup from the 2026-05-26 false-crash incident:
- runtime_root given as relative
- CWD changed to a worktree directory before shim exec
- fixture shim writes one byte to its received --runtime-dir agents/<id>/output.log

Smoke gate: requires ATDD_RUN_SMOKE=1.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="L002-SMOKE-001 requires ATDD_RUN_SMOKE=1",
)
def test_relative_runtime_root_output_log_lands_at_absolute_path(tmp_path, monkeypatch):
    from atdd.coach.commands.spawn import _build_shim_command, _verify_process_alive

    agent_id = "smoke-l002-bleed-gate"
    relative_suffix = ".atdd/runtime"

    # Set CWD to a directory that acts as the "original" coach CWD.
    original_cwd = tmp_path / "coach_cwd"
    original_cwd.mkdir()
    monkeypatch.chdir(original_cwd)

    # The resolved absolute runtime root (pre-CWD-change).
    expected_abs_runtime = original_cwd / relative_suffix

    # Build the shim command while CWD == original_cwd.
    # After E019 fix: --runtime-dir will be the absolute path.
    runtime_root_rel = Path(relative_suffix)
    cmd = _build_shim_command("echo ok", agent_id, runtime_root_rel)

    tokens = shlex.split(cmd)
    idx = tokens.index("--runtime-dir")
    received_runtime_dir = tokens[idx + 1]

    # ── Simulate CWD change to worktree ─────────────────────────────────────
    worktree_cwd = tmp_path / "worktree"
    worktree_cwd.mkdir()
    monkeypatch.chdir(worktree_cwd)

    # ── Fixture shim: writes one byte to agents/<id>/output.log at received path ──
    agent_out_dir = Path(received_runtime_dir) / "agents" / agent_id
    agent_out_dir.mkdir(parents=True, exist_ok=True)
    output_log = agent_out_dir / "output.log"
    output_log.write_bytes(b"L002 smoke heartbeat\n")

    # ── Assertions ──────────────────────────────────────────────────────────

    # 1. received --runtime-dir is absolute.
    assert Path(received_runtime_dir).is_absolute(), (
        f"L002-SMOKE-001: --runtime-dir in shim command must be absolute. "
        f"Got: {received_runtime_dir!r}"
    )

    # 2. output.log exists at the resolved absolute location (not at worktree-bled path).
    abs_output_log = expected_abs_runtime / "agents" / agent_id / "output.log"
    assert abs_output_log.exists(), (
        f"L002-SMOKE-001: output.log must exist at the pre-resolved absolute path "
        f"{abs_output_log}. Failing here means _build_shim_command did not resolve "
        "the relative runtime_root to absolute (CWD bleed reproduced)."
    )

    # 3. No output.log at the worktree-relative CWD-bled location.
    bled_log = worktree_cwd / relative_suffix / "agents" / agent_id / "output.log"
    assert not bled_log.exists(), (
        f"L002-SMOKE-001: output.log must NOT exist at the CWD-bled path {bled_log}."
    )

    # 4. _verify_process_alive does not raise (heartbeat visible at absolute path).
    class _AliveProc:
        def poll(self):
            return None

    _verify_process_alive(
        proc=_AliveProc(),
        agent_id=agent_id,
        runtime_dir=agent_out_dir,
        transport="cli-return",
        timeout_s=1.0,
    )
    # Must not raise ProcessNotAlive — the heartbeat byte is at the correct absolute path.
