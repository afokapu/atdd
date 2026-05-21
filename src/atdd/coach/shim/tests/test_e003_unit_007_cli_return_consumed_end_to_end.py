# URN: test:observe-and-correct:E003-UNIT-007-cli-return-consumed-end-to-end
# Acceptance: acc:observe-and-correct:E003-UNIT-007-cli-return-consumed-end-to-end
# WMBT: wmbt:observe-and-correct:E003
# Phase: RED
# Assertion: behavioral
# Layer: application
"""E003-UNIT-007 — A correction written to cli-return.jsonl by
InjectionDispatcher._dispatch_cli_return is consumed by the shim and
delivered to the agent CLI pty stdin in a single test fixture.

Closes the loop: dispatcher write → jsonl → shim read → pty bytes.

Issue #824.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def test_dispatcher_write_reaches_shim_pty(tmp_path):
    """InjectionDispatcher writes to cli-return.jsonl; the shim delivers it."""
    from atdd.coach.commands.observer import Correction, InjectionDispatcher
    from atdd.coach.shim import PersonaShim

    agent_id = "loop-close-001"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)

    captured_writes: list[bytes] = []

    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "60"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: captured_writes.append(data),
    )

    dispatcher = InjectionDispatcher()
    correction = Correction(
        agent_id=agent_id,
        rule_id="TEST-LAYOUT-001",
        severity=3,
        disposition="advisory",
        correction_text="Run atdd validate coder\n",
        injection_method="cli-return",
    )
    dispatcher.dispatch(correction, agent_dir=agent_dir)

    # The dispatcher wrote to cli-return.jsonl — now the shim should consume it
    shim.poll_once()

    assert len(captured_writes) == 1, "Dispatcher write did not reach shim"
    assert b"atdd validate coder" in captured_writes[0], (
        f"Expected correction text in pty write, got: {captured_writes}"
    )


def test_loop_closes_with_no_multiplexer_involved(tmp_path):
    """The end-to-end correction delivery path does NOT call multiplexer.send."""
    from atdd.coach.commands.observer import Correction, InjectionDispatcher
    from atdd.coach.shim import PersonaShim

    agent_id = "no-mux-001"
    agent_dir = tmp_path / "agents" / agent_id
    agent_dir.mkdir(parents=True)

    mux_send_called = []

    class FakeMux:
        def send(self, ref, text):
            mux_send_called.append((ref, text))

    captured_writes: list[bytes] = []
    shim = PersonaShim(
        agent_id=agent_id,
        spawn_command=["sleep", "60"],
        runtime_dir=tmp_path,
        pty_write_sink=lambda data: captured_writes.append(data),
    )

    dispatcher = InjectionDispatcher(multiplexer=FakeMux())
    correction = Correction(
        agent_id=agent_id,
        rule_id="TEST-LAYOUT-002",
        severity=3,
        disposition="advisory",
        correction_text="Correction via cli-return\n",
        injection_method="cli-return",
    )
    dispatcher.dispatch(correction, agent_dir=agent_dir)
    shim.poll_once()

    assert not mux_send_called, "multiplexer.send should NOT be called for cli-return corrections"
    assert len(captured_writes) == 1, "Expected one delivery to the shim pty"
