# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:E001-UNIT-001-pane-mode-default-when-cmux-workspace-id-set
# Acceptance: acc:dispatch-ux-defaults-and-primer:E001-UNIT-001-pane-mode-default-when-cmux-workspace-id-set
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E001
# Phase: RED
# Layer: application
# Runtime: python
"""E001-UNIT-001 — resolve_multiplexer_mode returns 'pane' when CMUX_WORKSPACE_ID is set.

RED: resolve_multiplexer_mode does not exist in coach.py yet. The CLI
unconditionally defaults multiplexer_mode to 'workspace'. This test pins the
helper contract: env-aware default resolution must return 'pane' when
CMUX_WORKSPACE_ID is present, 'workspace' when no mux env var is set, and
respect explicit_flag over any env var.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_pane_mode_when_cmux_workspace_id_set():
    """resolve_multiplexer_mode('pane') when CMUX_WORKSPACE_ID set and no explicit flag."""
    from atdd.coach.commands import coach

    fn = getattr(coach, "resolve_multiplexer_mode", None)
    assert fn is not None, (
        "coach.resolve_multiplexer_mode is not implemented — "
        "env-aware multiplexer default resolution is missing (RED)"
    )

    result = fn(explicit_flag=None, env={"CMUX_WORKSPACE_ID": "workspace:1"})
    assert result == "pane", (
        f"expected 'pane' when CMUX_WORKSPACE_ID is set, got {result!r}"
    )


def test_explicit_flag_wins_over_cmux_env():
    """An explicit --multiplexer-mode='workspace' overrides CMUX_WORKSPACE_ID."""
    from atdd.coach.commands import coach

    fn = getattr(coach, "resolve_multiplexer_mode", None)
    assert fn is not None, (
        "coach.resolve_multiplexer_mode is not implemented (RED)"
    )

    result = fn(
        explicit_flag="workspace",
        env={"CMUX_WORKSPACE_ID": "workspace:1"},
    )
    assert result == "workspace", (
        f"explicit_flag='workspace' must override env var; got {result!r}"
    )


def test_original_default_when_no_mux_env():
    """Without CMUX_WORKSPACE_ID or TMUX, the original default ('workspace') is returned."""
    from atdd.coach.commands import coach

    fn = getattr(coach, "resolve_multiplexer_mode", None)
    assert fn is not None, (
        "coach.resolve_multiplexer_mode is not implemented (RED)"
    )

    result = fn(explicit_flag=None, env={})
    assert result == "workspace", (
        f"without any mux env var, default must be 'workspace'; got {result!r}"
    )
