# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:E007-INTEGRATION-001-cmd-spawn-uses-surface-rpc
# Acceptance: acc:dispatch-ux-defaults-and-primer:E007-INTEGRATION-001-cmd-spawn-uses-surface-rpc
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E007
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E007-INTEGRATION-001 — cmd_spawn with multiplexer_mode='surface' uses new_surface_in_pane.

RED until _create_surface routes 'surface' mode through new_surface_in_pane on the
backend. Tests _create_surface end-to-end: resolve_focused_pane → new_surface_in_pane.
No new_workspace or new_surface(pane_ref=None) calls must appear.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


class _FullFakeMx:
    """FakeMultiplexer that supports all operations needed by _create_surface surface mode."""

    name = "fake"

    def __init__(self, focused_pane: str = "pane:4") -> None:
        self.calls: list[dict] = []
        self._focused_pane = focused_pane

    def resolve_focused_pane(self, workspace=None) -> str:
        self.calls.append({"op": "resolve_focused_pane"})
        return self._focused_pane

    def new_workspace(self, cwd: str, command: str, name=None) -> str:
        ref = f"workspace:{len(self.calls) + 1}"
        self.calls.append({"op": "new_workspace", "name": name, "ref": ref})
        return ref

    def new_surface(self, workspace_ref=None, pane_ref=None, cwd=None,
                    command=None, name=None, direction=None) -> str:
        ref = f"surface:{len(self.calls) + 1}"
        self.calls.append({"op": "new_surface", "pane_ref": pane_ref, "name": name, "ref": ref})
        return ref

    def new_surface_in_pane(self, pane_ref: str, cwd=None, command=None,
                             name=None, workspace=None) -> str:
        ref = f"surface:{len(self.calls) + 1}"
        self.calls.append({
            "op": "new_surface_in_pane",
            "pane_ref": pane_ref,
            "cwd": cwd,
            "command": command,
            "name": name,
            "ref": ref,
        })
        return ref


def test_surface_mode_end_to_end_resolves_pane_and_creates_surface(tmp_path):
    """_create_surface('surface') resolves the focused pane then calls new_surface_in_pane."""
    from atdd.coach.commands.spawn import _create_surface

    mx = _FullFakeMx(focused_pane="pane:4")
    ref = _create_surface(
        mx,
        worktree=tmp_path / "wt",
        command="claude --permission-mode acceptEdits",
        name="ATDD830",
        mode="surface",
    )

    ops = [c["op"] for c in mx.calls]
    assert "new_surface_in_pane" in ops, f"Expected new_surface_in_pane in ops; got {ops}"
    assert "new_workspace" not in ops, f"new_workspace must not be called; got {ops}"
    assert "new_surface" not in ops, f"new_surface(pane_ref=None) must not be called; got {ops}"

    spawn_call = next(c for c in mx.calls if c["op"] == "new_surface_in_pane")
    assert spawn_call["pane_ref"] == "pane:4", (
        f"Expected pane_ref='pane:4'; got {spawn_call['pane_ref']!r}"
    )
    assert ref.startswith("surface:"), f"Expected a surface ref; got {ref!r}"


def test_surface_mode_passes_cwd_and_command_to_backend(tmp_path):
    """_create_surface('surface') forwards cwd and command to new_surface_in_pane."""
    from atdd.coach.commands.spawn import _create_surface

    wt = tmp_path / "wt"
    cmd = "ATDD_AGENT_ID=planner-830-001 claude --permission-mode acceptEdits"

    mx = _FullFakeMx(focused_pane="pane:4")
    _create_surface(mx, worktree=wt, command=cmd, name="ATDD830", mode="surface")

    spawn_call = next(c for c in mx.calls if c["op"] == "new_surface_in_pane")
    assert spawn_call["cwd"] == str(wt), f"Expected cwd={str(wt)!r}; got {spawn_call['cwd']!r}"
    assert spawn_call["command"] == cmd, (
        f"Expected command={cmd!r}; got {spawn_call['command']!r}"
    )
    assert spawn_call["name"] == "ATDD830", (
        f"Expected name='ATDD830'; got {spawn_call['name']!r}"
    )


def test_auto_mode_also_uses_surface_in_pane(tmp_path):
    """'auto' mode (backward compat alias) must also route through new_surface_in_pane."""
    from atdd.coach.commands.spawn import _create_surface

    mx = _FullFakeMx(focused_pane="pane:2")
    _create_surface(mx, worktree=tmp_path, command="claude ...", name="ATDD830", mode="auto")

    ops = [c["op"] for c in mx.calls]
    assert "new_surface_in_pane" in ops, f"'auto' mode must use new_surface_in_pane; got {ops}"
    assert "new_workspace" not in ops
