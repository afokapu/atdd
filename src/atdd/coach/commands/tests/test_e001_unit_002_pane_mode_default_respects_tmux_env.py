# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:E001-UNIT-002-pane-mode-default-respects-tmux-env
# Acceptance: acc:dispatch-ux-defaults-and-primer:E001-UNIT-002-pane-mode-default-respects-tmux-env
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E001
# Phase: RED
# Layer: application
# Runtime: python
"""E001-UNIT-002 — resolve_multiplexer_mode returns 'pane' when TMUX is set (tmux parity).

RED: resolve_multiplexer_mode does not exist. TMUX env var (tmux backend) must
trigger the same pane-mode default as CMUX_WORKSPACE_ID does for the cmux
backend, maintaining parity across multiplexer backends.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_pane_mode_when_tmux_set():
    """resolve_multiplexer_mode returns 'pane' when TMUX is set and no explicit flag."""
    from atdd.coach.commands import coach

    fn = getattr(coach, "resolve_multiplexer_mode", None)
    assert fn is not None, (
        "coach.resolve_multiplexer_mode is not implemented — "
        "TMUX env parity for pane default is missing (RED)"
    )

    result = fn(
        explicit_flag=None,
        env={"TMUX": "/tmp/tmux-socket,12345,0"},
    )
    assert result == "pane", (
        f"expected 'pane' when TMUX is set, got {result!r}"
    )


def test_workspace_default_when_neither_mux_env_set():
    """Without CMUX_WORKSPACE_ID or TMUX, the original default is returned."""
    from atdd.coach.commands import coach

    fn = getattr(coach, "resolve_multiplexer_mode", None)
    assert fn is not None, (
        "coach.resolve_multiplexer_mode is not implemented (RED)"
    )

    result = fn(explicit_flag=None, env={})
    assert result == "workspace", (
        f"without mux env vars, default must be 'workspace'; got {result!r}"
    )
