# URN: test:spawn-agents:smoke-persona-spawn-integrity:E003-INTEGRATION-001-persona-pane-and-spawned-event
# Acceptance: acc:spawn-agents:E003-INTEGRATION-001-persona-pane-and-spawned-event
# WMBT: wmbt:spawn-agents:E003
# Phase: RED
# Layer: integration
"""E003-INTEGRATION-001 — a successful GREEN→SMOKE spawn gives the persona a
multiplexer surface and a schema-valid ``agent_spawned`` event.

Driving the coach spawn handler end-to-end for a GREEN→SMOKE transition
against a multiplexer that records every surface MUST yield: exactly one
persona multiplexer surface, an ``agent_spawned`` runtime event that
round-trips through ``runtime-event.schema.json`` with zero errors, and BOTH
the persona (``tester-<issue>-<suffix>/``) and observer
(``tester-<issue>-<suffix>-observer/``) runtime dirs.

RED: today the GREEN→SMOKE spawn never materialises an observer agent runtime
dir of its own, so the observer dir is absent after the call — this test
fails until the gated co-spawn (#733) lands.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import jsonschema
import pytest

import atdd
from atdd.coach.handlers.state_machine import (
    CoachContext,
    HandlerResult,
    Phase,
    Transition,
)

pytestmark = [pytest.mark.platform]

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
RUNTIME_EVENT_SCHEMA = (
    ATDD_PKG_DIR / "coach" / "schemas" / "runtime-event.schema.json"
)

SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-smoke-spawn-creates-observer-without-persona` |
| Train | `0002-coach-drives-lifecycle` |
"""


class _FakeMultiplexer:
    """Records every surface call. Non-bundling: ``new_persona_surface``
    creates ONLY the persona surface; the observer co-spawn is a separate
    call that ``cmd_spawn`` makes once the persona is confirmed (#733)."""

    name = "fake"

    def __init__(self, *, persona_materialises: bool = True) -> None:
        self.persona_materialises = persona_materialises
        self.calls: list[dict] = []
        self._surface_pane: dict[str, str] = {}

    def _record(self, op: str, **kw: Any) -> str:
        ref = f"surface:{len(self.calls) + 1}"
        self.calls.append({"op": op, "ref": ref, **kw})
        return ref

    def new_workspace(self, cwd: Any = None, command: Any = None, name: Any = None) -> str:
        return self._record("new_workspace", cwd=cwd, command=command, name=name)

    def new_surface(
        self,
        workspace_ref: Any = None,
        pane_ref: Any = None,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
        direction: Any = None,
    ) -> str:
        ref = self._record("new_surface", cwd=cwd, command=command, name=name)
        self._surface_pane[ref] = pane_ref or f"pane:{len(self.calls)}"
        return ref

    def new_surface_in_pane(
        self,
        pane_ref: str,
        cwd: Any = None,
        command: Any = None,
        name: Any = None,
    ) -> str:
        ref = self._record(
            "new_surface_in_pane", cwd=cwd, command=command, name=name, pane_ref=pane_ref
        )
        self._surface_pane[ref] = pane_ref
        return ref

    def surface_to_pane(self, surface_ref: str) -> str:
        return self._surface_pane.get(surface_ref, "pane:1")

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
    ) -> Optional[str]:
        if not self.persona_materialises:
            return None
        return self.new_surface(cwd=cwd, command=command, name=name)

    def rename(self, ref: str, name: str) -> None:
        self.calls.append({"op": "rename", "ref": ref, "name": name})

    def send(self, ref: str, text: str) -> None:
        pass

    def send_key(self, ref: str, key: str) -> None:
        pass

    def read_screen(self, ref: str, lines: int = 50) -> str:
        return ""

    def list_workspaces(self) -> list[str]:
        return []

    def close(self, ref: str) -> None:
        pass


def _spawn_ops(calls: list[dict]) -> list[dict]:
    return [
        c
        for c in calls
        if c["op"] in ("new_surface", "new_workspace", "new_surface_in_pane")
    ]


def test_green_to_smoke_spawn_gives_persona_pane_and_schema_valid_event(
    tmp_path, monkeypatch
):
    """handle() at GREEN→SMOKE records one persona surface, a schema-valid
    agent_spawned event, and both the persona and observer runtime dirs."""
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.commands import session_template
    from atdd.coach.commands import spawn as cmd_spawn_mod

    runtime_root = tmp_path / ".atdd" / "runtime"
    worktree = tmp_path / "wt"
    worktree.mkdir(parents=True)
    fake = _FakeMultiplexer(persona_materialises=True)

    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "smoke persona spawn", "body": SAMPLE_BODY},
    )
    monkeypatch.setattr(cmd_spawn_mod, "capture_session_uuid", lambda **kw: None)
    monkeypatch.setattr(
        cmd_spawn_mod, "_resolve_multiplexer", lambda preferred=None: fake
    )
    monkeypatch.setattr(
        spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "test prompt"
    )
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: worktree)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_root)

    ctx = CoachContext(issue_number=733, multiplexer_mode="pane")
    result = spawn_handler.handle(
        ctx, Transition(src=Phase.GREEN, dst=Phase.SMOKE)
    )

    assert result == HandlerResult.HANDLED, f"expected HANDLED, got {result}"

    agents_dir = runtime_root / "agents"
    assert agents_dir.is_dir(), f"agents dir never created: {agents_dir}"
    persona_dirs = [
        d
        for d in agents_dir.iterdir()
        if d.is_dir()
        and d.name.startswith("tester-733-")
        and not d.name.endswith("-observer")
    ]
    observer_dirs = [
        d for d in agents_dir.iterdir() if d.is_dir() and d.name.endswith("-observer")
    ]
    assert len(persona_dirs) == 1, (
        f"expected exactly one SMOKE persona dir, got {[d.name for d in persona_dirs]}"
    )
    assert len(observer_dirs) == 1, (
        f"expected exactly one observer dir alongside the persona, got "
        f"{[d.name for d in observer_dirs]} — observer-without-persona must "
        f"never occur (#733)"
    )

    # Exactly one persona multiplexer surface (observer surfaces carry the
    # `atdd observer run` command and are excluded).
    persona_surfaces = [
        c
        for c in _spawn_ops(fake.calls)
        if "atdd observer run" not in (c.get("command") or "")
    ]
    assert len(persona_surfaces) == 1, (
        f"expected exactly one persona surface, got {persona_surfaces}"
    )
    assert persona_surfaces[0]["ref"], "persona surface must return a surface ref"

    # The agent_spawned event round-trips through runtime-event.schema.json.
    events_path = persona_dirs[0] / "events.jsonl"
    assert events_path.is_file(), f"agent_spawned event stream missing: {events_path}"
    lines = [ln for ln in events_path.read_text().splitlines() if ln.strip()]
    assert lines, "events.jsonl is empty — no agent_spawned event written"
    record = json.loads(lines[0])
    schema = json.loads(RUNTIME_EVENT_SCHEMA.read_text())
    jsonschema.validate(record, schema)
    assert record["event_type"] == "agent_spawned"
