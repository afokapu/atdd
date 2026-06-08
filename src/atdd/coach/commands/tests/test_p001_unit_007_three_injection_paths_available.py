# URN: test:observe-and-correct:observer-runtime-and-rules:P001-UNIT-007-three-injection-paths-available
# Acceptance: acc:observe-and-correct:P001-UNIT-007-three-injection-paths-available
# WMBT: wmbt:observe-and-correct:P001
# Phase: RED
# Layer: application
"""P001-UNIT-007 — All three correction injection paths from §8.2 are
implemented and selectable per correction:
  1. CLI return-path (default)
  2. Multiplexer send-keys (via src/atdd/coach/utils/multiplexer.py)
  3. Kill-and-respawn (via coach respawn)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.platform]


class _StubMultiplexer:
    """In-memory stand-in for MultiplexerBackend to assert send-keys delivery."""

    name = "stub"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, ref: str, text: str) -> None:
        self.sent.append((ref, text))

    def send_key(self, ref: str, key: str) -> None:
        self.sent.append((ref, f"<key:{key}>"))


def test_dispatcher_supports_all_three_injection_methods():
    from atdd.coach.commands import observer

    dispatcher = observer.InjectionDispatcher()
    methods = set(dispatcher.supported_methods())
    assert methods == {"cli-return", "multiplexer-send", "respawn"}


def test_cli_return_dispatch_writes_to_return_channel(tmp_path: Path):
    """The default cli-return dispatch writes the correction text to a
    deterministic per-agent return-channel file the agent CLI reads."""
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    agent_dir = runtime / "agents" / "agent-A"
    agent_dir.mkdir(parents=True)

    dispatcher = observer.InjectionDispatcher()
    cor = observer.Correction(
        agent_id="agent-A",
        rule_id="coach.observer.bash-read-only-git-diagnostics",
        severity=3,
        disposition="advisory",
        correction_text="please correct yourself",
        injection_method="cli-return",
    )
    dispatcher.dispatch(cor, agent_dir=agent_dir)

    return_channel = agent_dir / "cli-return.jsonl"
    assert return_channel.exists(), (
        "cli-return must materialize the per-agent return-channel file"
    )
    content = return_channel.read_text()
    assert "please correct yourself" in content
    assert "coach.observer.bash-read-only-git-diagnostics" in content


def test_multiplexer_send_dispatch_invokes_multiplexer(tmp_path: Path):
    from atdd.coach.commands import observer

    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    mp = _StubMultiplexer()
    dispatcher = observer.InjectionDispatcher(
        multiplexer=mp,
        multiplexer_ref_for_agent=lambda agent_id: f"surface:{agent_id}",
    )

    cor = observer.Correction(
        agent_id="agent-A",
        rule_id="coach.observer.bash-read-only-git-diagnostics",
        severity=3,
        disposition="advisory",
        correction_text="nudge text",
        injection_method="multiplexer-send",
    )
    dispatcher.dispatch(cor, agent_dir=agent_dir)
    assert mp.sent == [("surface:agent-A", "nudge text")]


def test_respawn_dispatch_invokes_callback(tmp_path: Path):
    from atdd.coach.commands import observer

    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    calls: list[tuple[str, str]] = []
    dispatcher = observer.InjectionDispatcher(
        respawn_callback=lambda agent_id, reason: calls.append((agent_id, reason)),
    )

    cor = observer.Correction(
        agent_id="agent-A",
        rule_id="coach.observer.bash-read-only-git-diagnostics",
        severity=5,
        disposition="strict",
        correction_text="catastrophic failure — kill and respawn",
        injection_method="respawn",
    )
    dispatcher.dispatch(cor, agent_dir=agent_dir)
    assert calls == [("agent-A", "catastrophic failure — kill and respawn")]


def test_unsupported_injection_method_raises(tmp_path: Path):
    from atdd.coach.commands import observer

    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    dispatcher = observer.InjectionDispatcher()
    cor = observer.Correction(
        agent_id="agent-A",
        rule_id="coach.observer.bash-read-only-git-diagnostics",
        severity=3,
        disposition="advisory",
        correction_text="x",
        injection_method="cli-return",
    )
    object.__setattr__(cor, "injection_method", "made-up")
    with pytest.raises(ValueError):
        dispatcher.dispatch(cor, agent_dir=agent_dir)
