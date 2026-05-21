# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:E007-UNIT-001-surface-mode-calls-new-surface-in-pane
# Acceptance: acc:dispatch-ux-defaults-and-primer:E007-UNIT-001-surface-mode-calls-new-surface-in-pane
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E007
# Phase: RED
# Layer: application
"""E007-UNIT-001 — _create_surface with mode='surface' calls new_surface_in_pane.

RED until _create_surface's 'surface' mode is implemented to call
backend.new_surface_in_pane() instead of new_workspace or new_surface(pane_ref=None).
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


class _FakeMx:
    name = "fake"

    def __init__(self, focused_pane: str = "pane:1") -> None:
        self.calls: list[dict] = []
        self._focused_pane = focused_pane

    def resolve_focused_pane(self, workspace=None) -> str:
        return self._focused_pane

    def new_workspace(self, cwd: str, command: str, name=None) -> str:
        ref = f"workspace:{len(self.calls) + 1}"
        self.calls.append({"op": "new_workspace", "name": name, "ref": ref})
        return ref

    def new_surface(self, workspace_ref=None, pane_ref=None, cwd=None, command=None,
                    name=None, direction=None) -> str:
        ref = f"surface:{len(self.calls) + 1}"
        self.calls.append({"op": "new_surface", "pane_ref": pane_ref, "name": name, "ref": ref})
        return ref

    def new_surface_in_pane(self, pane_ref: str, cwd=None, command=None,
                             name=None, workspace=None) -> str:
        ref = f"surface:{len(self.calls) + 1}"
        self.calls.append({"op": "new_surface_in_pane", "pane_ref": pane_ref, "name": name, "ref": ref})
        return ref


def test_surface_mode_calls_new_surface_in_pane(tmp_path):
    """_create_surface('surface') must call new_surface_in_pane, not new_workspace."""
    from atdd.coach.commands.spawn import _create_surface

    mx = _FakeMx(focused_pane="pane:4")
    result = _create_surface(
        mx,
        worktree=tmp_path,
        command="claude ...",
        name="ATDD830",
        mode="surface",
    )

    ops = [c["op"] for c in mx.calls]
    assert "new_surface_in_pane" in ops, (
        f"Expected 'new_surface_in_pane' in ops; got {ops}"
    )
    assert "new_workspace" not in ops, (
        f"'new_workspace' must not be called in surface mode; got {ops}"
    )
    assert "new_surface" not in ops, (
        f"'new_surface' must not be called in surface mode; got {ops}"
    )
    assert result.startswith("surface:"), f"Expected a surface ref; got {result!r}"


def test_surface_mode_passes_resolved_pane_to_new_surface_in_pane(tmp_path):
    """The pane_ref passed to new_surface_in_pane must be the resolved focused pane."""
    from atdd.coach.commands.spawn import _create_surface

    mx = _FakeMx(focused_pane="pane:7")
    _create_surface(
        mx,
        worktree=tmp_path,
        command="claude ...",
        name="ATDD830",
        mode="surface",
    )

    surface_calls = [c for c in mx.calls if c["op"] == "new_surface_in_pane"]
    assert len(surface_calls) == 1
    assert surface_calls[0]["pane_ref"] == "pane:7", (
        f"Expected pane_ref='pane:7'; got {surface_calls[0]['pane_ref']!r}"
    )
