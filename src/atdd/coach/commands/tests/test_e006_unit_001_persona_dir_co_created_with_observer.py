# URN: test:spawn-agents:smoke-persona-spawn-integrity:E006-UNIT-001-persona-dir-co-created-with-observer
# Acceptance: acc:spawn-agents:E006-UNIT-001-persona-dir-co-created-with-observer
# WMBT: wmbt:spawn-agents:E006
# Phase: RED
# Layer: unit
"""E006-UNIT-001 — a successful GREEN→SMOKE ``cmd_spawn`` creates the persona
agent runtime dir, not only the ``-observer`` dir.

A GREEN→SMOKE spawn resolves the persona to ``tester`` (per
``_TRANSITION_PERSONA[(GREEN, SMOKE)]``). When ``cmd_spawn`` runs to
completion against a multiplexer backend that succeeds for both the persona
surface and the observer surface, the persona agent runtime dir
(``tester-<issue>-<suffix>/``) MUST exist with a written manifest — *in
addition to*, never *instead of*, the observer dir
(``tester-<issue>-<suffix>-observer/``).

RED: today ``cmd_spawn`` relies on the multiplexer's bundled
``new_persona_surface`` to co-spawn the observer and never materialises an
observer agent runtime dir of its own, so the observer dir is absent after
the call — this test fails until the gated co-spawn (#733) lands.
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
    """Records every surface call.

    Non-bundling: ``new_persona_surface`` creates ONLY the persona surface.
    The observer co-spawn is modelled as a separate call that ``cmd_spawn``
    is expected to make once the persona is confirmed materialised (#733).
    """

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
    """Keep ``cmd_spawn`` off the network and out of the 1.5 s session-uuid
    capture sleep."""
    from atdd.coach.commands import session_template
    from atdd.coach.commands import spawn as cmd_spawn_mod

    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "smoke persona spawn", "body": SAMPLE_BODY},
    )
    monkeypatch.setattr(cmd_spawn_mod, "capture_session_uuid", lambda **kw: None)


def test_green_to_smoke_cmd_spawn_creates_persona_dir_alongside_observer(
    tmp_path, monkeypatch
):
    """A completed GREEN→SMOKE ``cmd_spawn`` leaves a persona agent dir with a
    manifest *and* the matching observer dir."""
    from atdd.coach.commands import spawn

    _patch_offline(monkeypatch)

    worktree = tmp_path / "wt"
    worktree.mkdir()
    runtime = tmp_path / "rt"
    fake = _FakeMultiplexer(persona_materialises=True)
    agent_id = "tester-733-abcd1234"

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

    persona_dir = runtime / "agents" / agent_id
    observer_dir = runtime / "agents" / f"{agent_id}-observer"

    assert persona_dir.is_dir(), f"persona agent runtime dir missing: {persona_dir}"
    assert not persona_dir.name.endswith("-observer"), (
        f"persona dir must not carry the -observer suffix: {persona_dir.name}"
    )
    assert (persona_dir / "manifest.json").is_file(), (
        "persona dir must contain a written manifest (the _write_manifest step ran)"
    )
    assert observer_dir.is_dir(), (
        f"observer agent runtime dir missing: {observer_dir} — a GREEN→SMOKE "
        f"spawn must co-create the persona dir IN ADDITION TO the observer dir, "
        f"never an observer without a persona (#733)"
    )
