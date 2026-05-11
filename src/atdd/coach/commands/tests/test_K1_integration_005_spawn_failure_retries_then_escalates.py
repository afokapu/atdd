# URN: test:integration-hardening:coach-spawn-wiring:K001-INTEGRATION-005-spawn-failure-retries-then-escalates
# Acceptance: acc:integration-hardening:K001-INTEGRATION-005-spawn-failure-retries-then-escalates
# WMBT: wmbt:integration-hardening:K001
# Phase: RED
# Layer: integration
"""K001-INTEGRATION-005 — forced spawn failure retries (max_retries times) then escalates.

Verifies:
- _call_spawn is retried exactly max_retries+1 times total on persistent failure
- sleep intervals follow exponential backoff (1s, 2s, ...)
- escalation_channel receives the failure notification
- final state is recorded as BLOCKED in decisions.jsonl
- handle() returns HandlerResult.ERROR
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Phase, Transition

pytestmark = [pytest.mark.platform]


class _SpawnAlwaysFails:
    """Tracks call count; always raises an exception."""

    def __init__(self) -> None:
        self.call_count = 0

    def __call__(
        self,
        ctx: Any, persona: str, phase: str, llm: str,
        persona_prompt_content: str, worktree: Path,
        agent_id: str, runtime_root: Path,
    ) -> dict:
        self.call_count += 1
        raise RuntimeError("simulated spawn failure")


def _patch_handler(monkeypatch, tmp_path, spawn_handler, fake_spawn):
    monkeypatch.setattr(spawn_handler, "_call_spawn", fake_spawn)
    monkeypatch.setattr(
        spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt"
    )
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: tmp_path / "wt")
    runtime_root = tmp_path / ".atdd" / "runtime"
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_root)
    (tmp_path / "wt").mkdir(parents=True)
    return runtime_root


def test_retries_exactly_max_retries_plus_one_times(tmp_path, monkeypatch):
    """With max_retries=2, _call_spawn is called 3 times (1 initial + 2 retries)."""
    from atdd.coach.handlers import spawn as spawn_handler

    fake_spawn = _SpawnAlwaysFails()
    _patch_handler(monkeypatch, tmp_path, spawn_handler, fake_spawn)
    monkeypatch.setattr(spawn_handler.time, "sleep", lambda s: None)

    ctx = CoachContext(issue_number=585, max_retries=2)
    result = spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))

    assert result == HandlerResult.ERROR
    assert fake_spawn.call_count == 3, (
        f"expected 3 spawn attempts (1+2 retries), got {fake_spawn.call_count}"
    )


def test_exponential_backoff_delays(tmp_path, monkeypatch):
    """Sleep intervals must follow 1s, 2s, ... (doubling each retry)."""
    from atdd.coach.handlers import spawn as spawn_handler

    sleep_calls: list[float] = []
    monkeypatch.setattr(spawn_handler.time, "sleep", lambda s: sleep_calls.append(s))

    fake_spawn = _SpawnAlwaysFails()
    _patch_handler(monkeypatch, tmp_path, spawn_handler, fake_spawn)

    ctx = CoachContext(issue_number=585, max_retries=2)
    spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))

    assert sleep_calls == [1.0, 2.0], (
        f"expected exponential backoff [1.0, 2.0], got {sleep_calls}"
    )


def test_escalation_channel_notified_on_exhaustion(tmp_path, monkeypatch, capsys):
    """After exhaustion, the escalation channel must receive a message."""
    from atdd.coach.handlers import spawn as spawn_handler

    fake_spawn = _SpawnAlwaysFails()
    _patch_handler(monkeypatch, tmp_path, spawn_handler, fake_spawn)
    monkeypatch.setattr(spawn_handler.time, "sleep", lambda s: None)

    ctx = CoachContext(
        issue_number=585,
        max_retries=1,
        escalation_channel="slack://alerts",
    )
    spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))

    output = capsys.readouterr()
    combined = output.out + output.err
    assert "slack://alerts" in combined, (
        "escalation channel identifier must appear in output after exhaustion"
    )


def test_blocked_decision_written_on_exhaustion(tmp_path, monkeypatch):
    """After exhaustion, a BLOCKED abort decision is written to decisions.jsonl."""
    from atdd.coach.handlers import spawn as spawn_handler

    fake_spawn = _SpawnAlwaysFails()
    runtime_root = _patch_handler(monkeypatch, tmp_path, spawn_handler, fake_spawn)
    monkeypatch.setattr(spawn_handler.time, "sleep", lambda s: None)

    ctx = CoachContext(issue_number=585, max_retries=1)
    result = spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))

    assert result == HandlerResult.ERROR

    decisions_path = runtime_root / "coach" / "decisions.jsonl"
    assert decisions_path.is_file(), "decisions.jsonl must be written on spawn exhaustion"

    records = [
        json.loads(line) for line in decisions_path.read_text().splitlines() if line.strip()
    ]
    assert records, "at least one decision record expected"
    record = records[-1]
    assert record["issue_number"] == 585
    assert record["decision_type"] == "abort"
    assert record["outcome"].get("status") == "BLOCKED"
