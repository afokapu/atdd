# URN: test:observe-and-correct:worker-coach-event-loop:M005-UNIT-002-heartbeat-emission-is-adapter-agnostic
# Acceptance: acc:observe-and-correct:M005-UNIT-002-heartbeat-emission-is-adapter-agnostic
# WMBT: wmbt:observe-and-correct:M005
# Phase: RED
# Layer: application
"""M005-UNIT-002 — the heartbeat emission path is LLM-agnostic: the
observer never learns which adapter spawned the worker, and the heartbeat
is emitted through the generic ``atdd agent`` event path — not a
Claude-Code-specific hook.

Issue #731 Phase 2 — the emit mechanism MUST work identically for every
adapter in ``ADAPTER_REGISTRY`` (claude-code today; codex / gemini / glm
follow-ups).

RED: the observer emits no heartbeat at all, so the generic-path
assertions below cannot hold.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

OBSERVER_ID = "coder-731-hb02-observer"
WORKER_ID = "coder-731-hb02"


def _heartbeat_events(runtime: Path, worker_id: str) -> list[dict]:
    path = runtime / "agents" / worker_id / "events.jsonl"
    if not path.exists():
        return []
    records = [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]
    return [r for r in records if r.get("event_type") == "heartbeat"]


def test_observer_constructor_takes_no_adapter_or_llm_parameter(tmp_path):
    """Structural adapter-agnosticism: the observer is never told the LLM."""
    from atdd.coach.commands.observer import Observer

    params = set(inspect.signature(Observer.__init__).parameters)
    assert not (params & {"adapter", "llm", "adapter_name", "hook"})


def test_heartbeat_emitted_without_any_adapter_knowledge(tmp_path):
    from atdd.coach.commands.observer import Observer

    runtime = tmp_path / "rt"
    # Constructed with only generic args — no adapter/llm is ever supplied.
    obs = Observer(agent_id=OBSERVER_ID, runtime_dir=runtime, rules_dir=None)
    obs.scan_once()
    assert _heartbeat_events(runtime, WORKER_ID), (
        "no heartbeat emitted — the adapter-neutral emit path is missing"
    )


def test_heartbeat_uses_the_generic_agent_event_schema(tmp_path):
    """The heartbeat record has the LLM-neutral agent.cmd_event shape
    (event_type / agent_id / timestamp / payload) — proving it went
    through the shared event path, not a Claude-Code hook."""
    from atdd.coach.commands.observer import Observer

    runtime = tmp_path / "rt"
    obs = Observer(agent_id=OBSERVER_ID, runtime_dir=runtime, rules_dir=None)
    obs.scan_once()
    events = _heartbeat_events(runtime, WORKER_ID)
    assert events, "no heartbeat event emitted"
    record = events[0]
    assert set(record) >= {"event_type", "agent_id", "timestamp", "payload"}
    assert record["event_type"] == "heartbeat"
