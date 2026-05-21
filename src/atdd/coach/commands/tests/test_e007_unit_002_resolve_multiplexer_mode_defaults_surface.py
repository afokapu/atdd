# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:E007-UNIT-002-resolve-multiplexer-mode-defaults-surface
# Acceptance: acc:dispatch-ux-defaults-and-primer:E007-UNIT-002-resolve-multiplexer-mode-defaults-surface
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E007
# Phase: RED
# Layer: application
"""E007-UNIT-002 — resolve_multiplexer_mode defaults to 'surface' in all cases.

RED until resolve_multiplexer_mode returns 'surface' when CMUX_WORKSPACE_ID is
set (instead of the old 'pane') and when neither env var is set (instead of
the old 'workspace').
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_resolve_defaults_to_surface_when_cmux_workspace_id_set():
    """resolve_multiplexer_mode returns 'surface' when CMUX_WORKSPACE_ID is set."""
    from atdd.coach.commands.coach import resolve_multiplexer_mode

    result = resolve_multiplexer_mode(
        explicit_flag=None,
        env={"CMUX_WORKSPACE_ID": "workspace:1"},
    )
    assert result == "surface", (
        f"Expected 'surface' when CMUX_WORKSPACE_ID is set; got {result!r}"
    )


def test_resolve_defaults_to_surface_when_no_env():
    """resolve_multiplexer_mode returns 'surface' when no mux env vars are set."""
    from atdd.coach.commands.coach import resolve_multiplexer_mode

    result = resolve_multiplexer_mode(
        explicit_flag=None,
        env={},
    )
    assert result == "surface", (
        f"Expected 'surface' when no mux env set; got {result!r}"
    )


def test_resolve_respects_tmux_env():
    """resolve_multiplexer_mode returns 'surface' when TMUX is set."""
    from atdd.coach.commands.coach import resolve_multiplexer_mode

    result = resolve_multiplexer_mode(
        explicit_flag=None,
        env={"TMUX": "/tmp/tmux-12345,0,0"},
    )
    assert result == "surface", (
        f"Expected 'surface' when TMUX is set; got {result!r}"
    )


def test_resolve_explicit_flag_wins():
    """An explicit flag overrides the environment-based default."""
    from atdd.coach.commands.coach import resolve_multiplexer_mode

    result = resolve_multiplexer_mode(
        explicit_flag="surface",
        env={"CMUX_WORKSPACE_ID": "workspace:1"},
    )
    assert result == "surface"
