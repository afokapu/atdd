# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:E007-UNIT-003-deprecated-modes-raise-error
# Acceptance: acc:dispatch-ux-defaults-and-primer:E007-UNIT-003-deprecated-modes-raise-error
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E007
# Phase: RED
# Layer: application
"""E007-UNIT-003 — _create_surface raises DeprecatedMultiplexerModeError for workspace/pane modes.

RED until DeprecatedMultiplexerModeError is added to spawn.py and _create_surface
raises it for mode='workspace' and mode='pane'.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


class _FakeMx:
    name = "fake"

    def resolve_focused_pane(self, workspace=None) -> str:
        return "pane:1"

    def new_workspace(self, cwd, command, name=None):
        return "workspace:1"

    def new_surface(self, workspace_ref=None, pane_ref=None, cwd=None,
                    command=None, name=None, direction=None):
        return "surface:1"

    def new_surface_in_pane(self, pane_ref, cwd=None, command=None, name=None, workspace=None):
        return "surface:1"


def test_workspace_mode_raises_deprecated_error(tmp_path):
    """_create_surface with mode='workspace' must raise DeprecatedMultiplexerModeError."""
    from atdd.coach.commands.spawn import DeprecatedMultiplexerModeError, _create_surface

    with pytest.raises(DeprecatedMultiplexerModeError) as exc_info:
        _create_surface(
            _FakeMx(),
            worktree=tmp_path,
            command="claude ...",
            name="ATDD830",
            mode="workspace",
        )

    msg = str(exc_info.value)
    assert "new-workspace" in msg, f"Error message must reference 'new-workspace'; got: {msg!r}"
    assert "surface" in msg, f"Error message must reference 'surface' mode; got: {msg!r}"


def test_pane_mode_raises_deprecated_error(tmp_path):
    """_create_surface with mode='pane' must raise DeprecatedMultiplexerModeError."""
    from atdd.coach.commands.spawn import DeprecatedMultiplexerModeError, _create_surface

    with pytest.raises(DeprecatedMultiplexerModeError) as exc_info:
        _create_surface(
            _FakeMx(),
            worktree=tmp_path,
            command="claude ...",
            name="ATDD830",
            mode="pane",
        )

    msg = str(exc_info.value)
    assert "new-pane" in msg, f"Error message must reference 'new-pane'; got: {msg!r}"
    assert "surface" in msg, f"Error message must reference 'surface' mode; got: {msg!r}"


def test_deprecated_error_is_value_error_subclass():
    """DeprecatedMultiplexerModeError must be a ValueError subclass."""
    from atdd.coach.commands.spawn import DeprecatedMultiplexerModeError

    assert issubclass(DeprecatedMultiplexerModeError, ValueError), (
        "DeprecatedMultiplexerModeError must be a ValueError subclass"
    )
