# URN: test:spawn-agents:atdd-spawn-skeleton-and-harness:E001-CONTRACT-001-agent-spawned-event-conforms
# Acceptance: acc:spawn-agents:E001-CONTRACT-001-agent-spawned-event-conforms
# WMBT: wmbt:spawn-agents:E001
# Phase: RED
# Layer: contract
"""E001-CONTRACT-001 — the ``agent_spawned`` event written by ``atdd
spawn`` MUST round-trip through ``runtime-event.schema.json`` with zero
validation errors; its producer / triggering condition / idempotency /
ordering / replay semantics match the ``agent_spawned`` subsection of
``event-semantics.md`` (frozen at #483).

Issue #499.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import jsonschema
import pytest

import atdd

pytestmark = [pytest.mark.platform]

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
RUNTIME_EVENT_SCHEMA = (
    ATDD_PKG_DIR / "coach" / "schemas" / "runtime-event.schema.json"
)
EVENT_SEMANTICS_DOC = (
    ATDD_PKG_DIR / "coach" / "schemas" / "event-semantics.md"
)


SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/spawn-test` |
| Train | `0002-coach-drives-lifecycle` |
| Feature | contract test |
"""


class FakeMultiplexer:
    name = "fake"

    def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> str:
        return "workspace:1"

    def new_surface(
        self,
        workspace_ref: Optional[str] = None,
        pane_ref: Optional[str] = None,
        cwd: Optional[str] = None,
        command: Optional[str] = None,
        name: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> str:
        return "surface:1"

    def new_persona_surface(
        self,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
        *,
        observer_runtime_root: str = "",
        observer_agent_id: str = "",
        observer_name: str = "",
        observer_command: str = "",
        **_: Any,
    ) -> str:
        persona_ref = self.new_surface(cwd=cwd, command=command, name=name)
        try:
            self.new_surface(cwd=cwd, command=observer_command, name=observer_name)
        except Exception:
            pass
        return persona_ref


def _spawn(tmp_path: Path, monkeypatch, *, agent_id: str = "coder-358-001"):
    from atdd.coach.commands import spawn
    from atdd.coach.commands import session_template

    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": SAMPLE_BODY},
    )
    worktree = tmp_path / "wt"
    worktree.mkdir(exist_ok=True)
    runtime = tmp_path / "rt"
    spawn.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=worktree,
        issue=358,
        agent_id=agent_id,
        runtime_root=runtime,
        multiplexer=FakeMultiplexer(),
    )
    return runtime / "agents" / agent_id / "events.jsonl"


def _read_first_event(events_path: Path) -> dict:
    lines = [ln for ln in events_path.read_text().splitlines() if ln.strip()]
    return json.loads(lines[0])


# ---------------------------------------------------------------------------
# Schema conformance
# ---------------------------------------------------------------------------


def test_agent_spawned_event_round_trips_through_runtime_event_schema(tmp_path, monkeypatch):
    """The emitted event MUST validate against runtime-event.schema.json
    with zero errors."""
    events_path = _spawn(tmp_path, monkeypatch)
    schema = json.loads(RUNTIME_EVENT_SCHEMA.read_text())
    record = _read_first_event(events_path)

    jsonschema.validate(record, schema)
    assert record["event_type"] == "agent_spawned"
    assert "timestamp" in record
    assert "payload" in record


def test_agent_spawned_event_has_no_extra_top_level_keys(tmp_path, monkeypatch):
    """``runtime-event.schema.json`` is ``additionalProperties: false`` —
    the producer MUST NOT add unenumerated top-level keys."""
    events_path = _spawn(tmp_path, monkeypatch)
    record = _read_first_event(events_path)
    allowed = {"event_type", "agent_id", "timestamp", "payload"}
    assert set(record.keys()) <= allowed


def test_timestamp_is_iso_8601_utc(tmp_path, monkeypatch):
    """``timestamp`` is RFC-3339 / ISO-8601 UTC; per the agent.py
    convention, must end with ``Z``."""
    events_path = _spawn(tmp_path, monkeypatch)
    record = _read_first_event(events_path)
    assert record["timestamp"].endswith("Z")


# ---------------------------------------------------------------------------
# Semantics conformance — event-semantics.md `agent_spawned` subsection
# ---------------------------------------------------------------------------


def test_event_semantics_doc_documents_agent_spawned():
    """Anchor: the frozen ``event-semantics.md`` must continue to
    enumerate ``agent_spawned`` as one of the 12 event types and to
    document its producer / triggering / idempotency / ordering / replay
    semantics. Without this anchor the `Replay cached` / per-agent total
    order claims that downstream tests rest on are unverified."""
    text = EVENT_SEMANTICS_DOC.read_text()
    section = text.split("## `agent_spawned`", 1)
    assert len(section) == 2, "event-semantics.md missing `agent_spawned` section"
    body = section[1].split("## `", 1)[0]
    for label in ("Producer", "Triggering condition", "Idempotency", "Ordering", "Replay"):
        assert label in body, f"agent_spawned subsection missing **{label}**"


def test_payload_documents_persona_llm_worktree_for_observers(tmp_path, monkeypatch):
    """Per spec §5.2 + §4.5, the ``agent_spawned`` payload carries the
    spawn-time decision context (persona, llm, worktree, surface_ref,
    issue) so the observer rule ``14-canonical-naming-drift`` (#L1) and
    other downstream consumers can correlate spawn-time decisions with
    later events without re-reading the issue body."""
    events_path = _spawn(tmp_path, monkeypatch)
    record = _read_first_event(events_path)
    payload = record["payload"]
    assert payload["persona"] == "coder"
    assert payload["llm"] == "claude-code"
    assert payload["issue"] == 358
    assert payload["surface_ref"]
    assert payload["worktree"]
    # The K1 spawn flow must emit at least one rule-ID per spec §7.1 +
    # acceptance E001 (rule-ID emission). The canonical anchor is
    # ``coach.spawn.atdd-spawn-cli`` (or equivalent canonical anchor).
    assert "rule_id" in payload
    assert payload["rule_id"].startswith("coach.spawn.")


def test_idempotency_per_agent_id(tmp_path, monkeypatch):
    """Per event-semantics.md ``agent_spawned`` is **exactly-once** per
    ``agent_id`` per coach run. K1's spawn writes each spawn into the
    per-agent events.jsonl; two separate agent_ids MUST produce two
    independent events.jsonl files (per-agent total order)."""
    events_a = _spawn(tmp_path, monkeypatch, agent_id="coder-358-A")
    events_b = _spawn(tmp_path, monkeypatch, agent_id="coder-358-B")
    rec_a = _read_first_event(events_a)
    rec_b = _read_first_event(events_b)
    assert rec_a["agent_id"] == "coder-358-A"
    assert rec_b["agent_id"] == "coder-358-B"
    # Per-agent total order: each stream's first event is the spawn event.
    assert rec_a["event_type"] == "agent_spawned"
    assert rec_b["event_type"] == "agent_spawned"
