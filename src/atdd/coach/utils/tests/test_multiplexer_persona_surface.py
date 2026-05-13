# URN: test:integration-hardening:coach-single-command-driver:L003-UNIT-001-multiplexer-abc-supports-new-persona-surface
# Acceptance: acc:integration-hardening:L003-UNIT-001-multiplexer-abc-supports-new-persona-surface
# Acceptance: acc:integration-hardening:L003-UNIT-002-spawn-observer-removed-from-handler
# Acceptance: acc:integration-hardening:L003-UNIT-003-observer-failure-structured-logged
# WMBT: wmbt:integration-hardening:L003
# Phase: RED
# Layer: unit
"""L003-UNIT-001/003 — MultiplexerBackend.new_persona_surface primitive.

Tests:
- FakeMultiplexer.new_persona_surface records both spawns (persona + observer)
  and tracks in new_persona_surface_calls
- MultiplexerBackend default implementation emits structured JSON log to stderr
  on observer failure; persona spawn still succeeds (no exception raised)
- CmuxBackend inherits the default (no override needed)
"""
from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

import pytest

from atdd.coach.utils.multiplexer import (
    FakeMultiplexer,
    MultiplexerBackend,
    MultiplexerError,
)


# ---------------------------------------------------------------------------
# FakeMultiplexer.new_persona_surface
# ---------------------------------------------------------------------------


class TestFakeMultiplexerPersonaSurface:
    def test_returns_persona_ref(self):
        mx = FakeMultiplexer()
        ref = mx.new_persona_surface(
            cwd="/wt",
            command="claude run",
            name="ATDD999-persona",
            observer_runtime_root="/rt",
            observer_agent_id="agent-obs",
            observer_name="ATDD999-observer-planned",
            observer_command="atdd observer run --agent-id agent-obs",
        )
        assert ref.startswith("surface:"), f"Expected surface ref, got {ref!r}"

    def test_records_in_new_persona_surface_calls(self):
        mx = FakeMultiplexer()
        mx.new_persona_surface(
            cwd="/wt",
            command="claude run",
            name="ATDD999-persona",
            observer_runtime_root="/rt",
            observer_agent_id="agent-obs",
            observer_name="ATDD999-observer-planned",
            observer_command="atdd observer run --agent-id agent-obs",
        )
        assert len(mx.new_persona_surface_calls) == 1
        call = mx.new_persona_surface_calls[0]
        assert call["persona_name"] == "ATDD999-persona"
        assert call["observer_name"] == "ATDD999-observer-planned"
        assert call["observer_agent_id"] == "agent-obs"

    def test_records_two_new_surface_calls_in_calls(self):
        mx = FakeMultiplexer()
        mx.new_persona_surface(
            cwd="/wt",
            command="claude run",
            name="ATDD999-persona",
            observer_runtime_root="/rt",
            observer_agent_id="agent-obs",
            observer_name="ATDD999-observer-planned",
            observer_command="atdd observer run --agent-id agent-obs",
        )
        surface_calls = [c for c in mx.calls if c["op"] == "new_surface"]
        assert len(surface_calls) == 2

    def test_persona_ref_in_calls_first(self):
        mx = FakeMultiplexer()
        ref = mx.new_persona_surface(
            cwd="/wt",
            command="claude run",
            name="ATDD999-persona",
            observer_runtime_root="/rt",
            observer_agent_id="agent-obs",
            observer_name="ATDD999-observer-planned",
            observer_command="atdd observer run --agent-id agent-obs",
        )
        surface_calls = [c for c in mx.calls if c["op"] == "new_surface"]
        assert surface_calls[0]["ref"] == ref
        assert surface_calls[0]["name"] == "ATDD999-persona"

    def test_observer_ref_in_calls_second(self):
        mx = FakeMultiplexer()
        mx.new_persona_surface(
            cwd="/wt",
            command="claude run",
            name="ATDD999-persona",
            observer_runtime_root="/rt",
            observer_agent_id="agent-obs",
            observer_name="ATDD999-observer-planned",
            observer_command="atdd observer run --agent-id agent-obs",
        )
        surface_calls = [c for c in mx.calls if c["op"] == "new_surface"]
        assert surface_calls[1]["name"] == "ATDD999-observer-planned"
        assert "agent-obs" in (surface_calls[1].get("command") or "")

    def test_multiple_calls_accumulate_in_new_persona_surface_calls(self):
        mx = FakeMultiplexer()
        mx.new_persona_surface(
            cwd="/wt1", command="c1", name="p1",
            observer_runtime_root="/r", observer_agent_id="o1",
            observer_name="obs1", observer_command="cmd1",
        )
        mx.new_persona_surface(
            cwd="/wt2", command="c2", name="p2",
            observer_runtime_root="/r", observer_agent_id="o2",
            observer_name="obs2", observer_command="cmd2",
        )
        assert len(mx.new_persona_surface_calls) == 2


# ---------------------------------------------------------------------------
# MultiplexerBackend default — observer failure → structured stderr log
# ---------------------------------------------------------------------------


class _BackendFailingObserver(MultiplexerBackend):
    """Backend where new_surface succeeds once (persona), fails on second call (observer)."""

    name = "test-failing-observer"

    def __init__(self) -> None:
        self._call_count = 0
        self.persona_ref: str = ""

    def new_surface(  # type: ignore[override]
        self,
        workspace_ref=None, pane_ref=None,
        cwd=None, command=None, name=None, direction=None,
    ) -> str:
        self._call_count += 1
        if self._call_count == 1:
            self.persona_ref = f"surface:{self._call_count}"
            return self.persona_ref
        raise MultiplexerError("observer surface unavailable")

    def new_workspace(self, cwd, command, name=None):  # type: ignore[override]
        return "workspace:1"

    def read_screen(self, ref, lines=50):  # type: ignore[override]
        return ""

    def send(self, ref, text):  # type: ignore[override]
        pass

    def send_key(self, ref, key):  # type: ignore[override]
        pass

    def list_workspaces(self):  # type: ignore[override]
        return []

    def close(self, ref):  # type: ignore[override]
        pass


class TestMultiplexerBackendDefaultPersonaSurface:
    def test_observer_failure_returns_persona_ref(self, capsys):
        backend = _BackendFailingObserver()
        ref = backend.new_persona_surface(
            cwd="/wt",
            command="claude run",
            name="ATDD999-persona",
            observer_runtime_root="/rt",
            observer_agent_id="agent-obs",
            observer_name="ATDD999-observer-planned",
            observer_command="atdd observer run",
        )
        assert ref == "surface:1", f"Expected persona ref surface:1, got {ref!r}"

    def test_observer_failure_does_not_raise(self, capsys):
        backend = _BackendFailingObserver()
        # Must not raise even though observer spawn fails
        backend.new_persona_surface(
            cwd="/wt",
            command="claude run",
            name="ATDD999-persona",
            observer_runtime_root="/rt",
            observer_agent_id="agent-obs",
            observer_name="ATDD999-observer-planned",
            observer_command="atdd observer run",
        )

    def test_observer_failure_emits_structured_json_to_stderr(self, capsys):
        backend = _BackendFailingObserver()
        backend.new_persona_surface(
            cwd="/wt",
            command="claude run",
            name="ATDD999-persona",
            observer_runtime_root="/rt",
            observer_agent_id="agent-obs",
            observer_name="ATDD999-observer-planned",
            observer_command="atdd observer run",
        )
        captured = capsys.readouterr()
        assert captured.err.strip(), "Expected structured error on stderr"
        event = json.loads(captured.err.strip())
        assert event["event"] == "observer_cospawn_failed"
        assert "observer" in event.get("observer_name", "").lower()
        assert "error" in event

    def test_persona_surface_called_once_before_observer_failure(self, capsys):
        backend = _BackendFailingObserver()
        backend.new_persona_surface(
            cwd="/wt",
            command="claude run",
            name="ATDD999-persona",
            observer_runtime_root="/rt",
            observer_agent_id="agent-obs",
            observer_name="ATDD999-observer-planned",
            observer_command="atdd observer run",
        )
        assert backend._call_count == 2, (
            f"Expected 2 new_surface calls (1 persona + 1 observer attempt), got {backend._call_count}"
        )
