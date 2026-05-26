# URN: test:spawn-agents:E021-UNIT-002-timeout-names-bleed-path-when-candidate-found
# Acceptance: acc:spawn-agents:E021-UNIT-002-timeout-names-bleed-path-when-candidate-found
# WMBT: wmbt:spawn-agents:E021
# Phase: GREEN
# Assertion: behavioral
"""E021-UNIT-002 — when output.log is absent at the polled path but present at a
CWD-bleed candidate, ProcessNotAlive message:
  1. says "path-mismatch" or "found at" (makes the root cause explicit)
  2. names BOTH the expected (polled) path and the found (alternate) path
  3. does NOT say "shim may have crashed silently" (crash is ruled out)

This is the diagnostic that turns a 45-minute false-crash investigation into a
30-second read (reproduced 2026-05-26 on issue #860).

RED: fails until _verify_process_alive scans CWD-relative bleed candidates and
emits a "path-mismatch" message when a candidate is found.
"""
from __future__ import annotations

from pathlib import Path

import pytest


class _AliveProc:
    def poll(self):
        return None


def test_timeout_emits_path_mismatch_when_bleed_candidate_found(tmp_path, monkeypatch):
    from atdd.coach.commands.spawn import ProcessNotAlive, _verify_process_alive

    agent_id = "unit-e021-002-bleed"

    # Coach's expected location — output.log does NOT exist here.
    polled_runtime_dir = tmp_path / "abs_runtime" / "agents" / agent_id
    polled_runtime_dir.mkdir(parents=True)

    # The CWD-bleed location — output.log DOES exist here (shim wrote to bled path).
    # The bleed candidate follows the pattern: CWD / <common-runtime-suffix> / agents / id.
    bleed_cwd = tmp_path / "worktree_cwd"
    bleed_cwd.mkdir()
    bleed_agent_dir = bleed_cwd / ".atdd" / "runtime" / "agents" / agent_id
    bleed_agent_dir.mkdir(parents=True)
    (bleed_agent_dir / "output.log").write_bytes(b"shim alive but bled\n")

    # Set CWD to the worktree so the implementation can detect the candidate.
    monkeypatch.chdir(bleed_cwd)

    with pytest.raises(ProcessNotAlive) as exc_info:
        _verify_process_alive(
            proc=_AliveProc(),
            agent_id=agent_id,
            runtime_dir=polled_runtime_dir,
            transport="cli-return",
            timeout_s=0.05,
        )

    msg = str(exc_info.value)

    # 1. "path-mismatch" or "found at" must appear.
    has_mismatch_marker = any(
        phrase in msg.lower()
        for phrase in ["path-mismatch", "found at", "alternate path", "bleed candidate found"]
    )
    assert has_mismatch_marker, (
        f"E021-UNIT-002: ProcessNotAlive must say 'path-mismatch' or 'found at' when a "
        f"bleed candidate is detected. Got: {msg!r}"
    )

    # 2. The expected (polled) path must be named.
    expected_log = str(polled_runtime_dir / "output.log")
    assert expected_log in msg, (
        f"E021-UNIT-002: message must name the polled (expected) path {expected_log!r}. "
        f"Got: {msg!r}"
    )

    # 3. The found (alternate) bleed path must be named.
    found_log = str(bleed_agent_dir / "output.log")
    assert found_log in msg, (
        f"E021-UNIT-002: message must name the found (alternate) path {found_log!r}. "
        f"Got: {msg!r}"
    )

    # 4. "crashed silently" must NOT appear (crash is ruled out by the found candidate).
    assert "crashed silently" not in msg, (
        f"E021-UNIT-002: when a bleed candidate is found, the message must NOT say "
        f"'crashed silently'. Got: {msg!r}"
    )


def test_path_mismatch_message_omits_crash_phrasing(tmp_path, monkeypatch):
    from atdd.coach.commands.spawn import ProcessNotAlive, _verify_process_alive

    agent_id = "unit-e021-002-nocrash"
    polled_dir = tmp_path / "rt" / "agents" / agent_id
    polled_dir.mkdir(parents=True)

    bleed_cwd = tmp_path / "wt"
    bleed_cwd.mkdir()
    bleed_dir = bleed_cwd / ".atdd" / "runtime" / "agents" / agent_id
    bleed_dir.mkdir(parents=True)
    (bleed_dir / "output.log").write_bytes(b"alive\n")

    monkeypatch.chdir(bleed_cwd)

    with pytest.raises(ProcessNotAlive) as exc_info:
        _verify_process_alive(
            proc=_AliveProc(),
            agent_id=agent_id,
            runtime_dir=polled_dir,
            transport="cli-return",
            timeout_s=0.05,
        )

    msg = str(exc_info.value)
    assert "crashed silently" not in msg, (
        f"E021-UNIT-002: path-mismatch case must not say 'crashed silently'. Got: {msg!r}"
    )
