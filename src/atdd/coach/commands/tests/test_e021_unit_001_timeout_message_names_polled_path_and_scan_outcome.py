# URN: test:spawn-agents:E021-UNIT-001-timeout-message-names-polled-path-and-scan-outcome
# Acceptance: acc:spawn-agents:E021-UNIT-001-timeout-message-names-polled-path-and-scan-outcome
# WMBT: wmbt:spawn-agents:E021
# Phase: GREEN
# Assertion: behavioral
"""E021-UNIT-001 — when _verify_process_alive times out (proc alive, output.log absent,
no CWD-bleed candidate found), the ProcessNotAlive message:
  1. names the absolute path being polled
  2. includes a note indicating no alternate bleed candidate was located

This turns a generic "crashed silently" message into an actionable diagnostic.

RED: fails until _verify_process_alive scans for bleed candidates and includes a
"no alternate" / "no candidate" note in the timeout message.
"""
from __future__ import annotations

from pathlib import Path

import pytest


class _AliveProc:
    """Fake process that never exits."""

    def poll(self):
        return None


def test_timeout_message_names_absolute_polled_path(tmp_path):
    from atdd.coach.commands.spawn import ProcessNotAlive, _verify_process_alive

    agent_id = "unit-e021-001-nopath"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    # output.log does NOT exist — shim never wrote a heartbeat

    with pytest.raises(ProcessNotAlive) as exc_info:
        _verify_process_alive(
            proc=_AliveProc(),
            agent_id=agent_id,
            runtime_dir=agent_dir,
            transport="cli-return",
            timeout_s=0.05,
        )

    msg = str(exc_info.value)
    expected_log_path = str(agent_dir / "output.log")

    assert expected_log_path in msg, (
        f"E021-UNIT-001: ProcessNotAlive message must name the absolute polled path "
        f"{expected_log_path!r}. Got: {msg!r}"
    )


def test_timeout_message_includes_no_candidate_note_when_bleed_absent(tmp_path, monkeypatch):
    from atdd.coach.commands.spawn import ProcessNotAlive, _verify_process_alive

    agent_id = "unit-e021-001-nocandidate"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    # No output.log anywhere — no bleed candidate

    # Change CWD so the scan has a defined location to check and finds nothing.
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ProcessNotAlive) as exc_info:
        _verify_process_alive(
            proc=_AliveProc(),
            agent_id=agent_id,
            runtime_dir=agent_dir,
            transport="cli-return",
            timeout_s=0.05,
        )

    msg = str(exc_info.value)
    # The message must indicate that the bleed-candidate scan ran and found nothing.
    # Acceptable phrases: "no alternate", "no candidate", "bleed candidate: none",
    # "no bleed candidate", "not found at alternate", etc.
    has_no_candidate_note = any(
        phrase in msg.lower()
        for phrase in [
            "no alternate",
            "no candidate",
            "no bleed",
            "candidate: none",
            "not found at alternate",
        ]
    )
    assert has_no_candidate_note, (
        f"E021-UNIT-001: ProcessNotAlive message must include a note indicating the "
        f"bleed-candidate scan found nothing. Got: {msg!r}. "
        "Fix: add bleed-candidate scan to _verify_process_alive timeout handler."
    )
