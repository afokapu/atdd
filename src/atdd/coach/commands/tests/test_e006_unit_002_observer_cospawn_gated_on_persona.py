# URN: test:spawn-agents:smoke-persona-spawn-integrity:E006-UNIT-002-observer-cospawn-gated-on-persona
# Acceptance: acc:spawn-agents:E006-UNIT-002-observer-cospawn-gated-on-persona
# WMBT: wmbt:spawn-agents:E006
# Phase: RED
# Layer: unit
"""E006-UNIT-002 — when the persona spawn step fails, the observer co-spawn is
never reached and no orphan observer is created.

A GREEN→SMOKE ``cmd_spawn`` against a multiplexer whose persona spawn step
(persona pane creation / adapter dispatch) fails — no persona surface is
produced — MUST surface that failure loudly: ``cmd_spawn`` raises rather than
returning a truthy success dict, the observer co-spawn is never reached, and
no orphan observer surface or runtime dir is left behind.

RED: today ``cmd_spawn`` continues past a falsy persona ``surface_ref`` —
running ``cmd_event`` and ``_write_manifest`` and returning a truthy result
dict — so it does not raise. This test fails until the persona-materialisation
gate (#733) lands.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]

SAMPLE_BODY = """## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `feat/coach-smoke-spawn-creates-observer-without-persona` |
| Train | `0002-coach-drives-lifecycle` |
"""


class _FakeMultiplexer:
    """Records every surface call. ``persona_materialises=False`` models a
    persona spawn step that fails to produce a persona surface (#733)."""

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


def _patch_offline(monkeypatch) -> None:
    from atdd.coach.commands import session_template
    from atdd.coach.commands import spawn as cmd_spawn_mod

    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "smoke persona spawn", "body": SAMPLE_BODY},
    )
    monkeypatch.setattr(cmd_spawn_mod, "capture_session_uuid", lambda **kw: None)


def test_failed_persona_spawn_is_loud_and_leaves_no_orphan_observer(
    tmp_path, monkeypatch
):
    """A persona spawn that fails to materialise must raise, never co-spawn the
    observer, and leave no orphan observer surface or dir."""
    from atdd.coach.commands import spawn

    _patch_offline(monkeypatch)

    worktree = tmp_path / "wt"
    worktree.mkdir()
    runtime = tmp_path / "rt"
    fake = _FakeMultiplexer(persona_materialises=False)
    agent_id = "tester-733-fail0001"

    raised = False
    try:
        spawn.cmd_spawn(
            persona="tester",
            llm="claude-code",
            worktree=worktree,
            issue=733,
            agent_id=agent_id,
            runtime_root=runtime,
            phase="smoke",
            multiplexer=fake,
        )
    except Exception:
        raised = True

    assert raised, (
        "cmd_spawn must raise loudly when the persona surface fails to "
        "materialise — returning a truthy success dict silently produces the "
        "observer-without-persona stall (#733)"
    )

    observer_dir = runtime / "agents" / f"{agent_id}-observer"
    assert not observer_dir.exists(), (
        f"observer co-spawn was reached despite a failed persona spawn: "
        f"{observer_dir}"
    )

    observer_surfaces = [
        c for c in fake.calls if "atdd observer run" in (c.get("command") or "")
    ]
    assert not observer_surfaces, (
        f"no observer surface must be created when the persona fails; got "
        f"{observer_surfaces}"
    )
