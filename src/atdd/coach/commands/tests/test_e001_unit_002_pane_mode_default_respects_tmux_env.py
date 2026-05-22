# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:E001-UNIT-002-pane-mode-default-respects-tmux-env
# Acceptance: acc:dispatch-ux-defaults-and-primer:E001-UNIT-002-pane-mode-default-respects-tmux-env
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E001
# Phase: GREEN
# Layer: application
# Runtime: python
"""E001-UNIT-002 — resolve_multiplexer_mode returns 'surface' unconditionally (E007 supersedes).

GREEN: E007 (#830) superseded E001's 'pane' fix — cmux new-pane is also
deprecated (Broken pipe on cmux >=0.64.7). The function now unconditionally
returns 'surface' when no explicit flag is given, regardless of env vars.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_surface_mode_when_tmux_set():
    """resolve_multiplexer_mode returns 'surface' when TMUX is set (E007: pane is also deprecated)."""
    from atdd.coach.commands import coach

    fn = getattr(coach, "resolve_multiplexer_mode", None)
    assert fn is not None, "coach.resolve_multiplexer_mode is not implemented"

    result = fn(
        explicit_flag=None,
        env={"TMUX": "/tmp/tmux-socket,12345,0"},
    )
    assert result == "surface", (
        f"expected 'surface' when TMUX is set (E007: 'pane' is deprecated), got {result!r}"
    )


def test_surface_default_when_neither_mux_env_set():
    """Without CMUX_WORKSPACE_ID or TMUX, 'surface' is the unconditional default."""
    from atdd.coach.commands import coach

    fn = getattr(coach, "resolve_multiplexer_mode", None)
    assert fn is not None, "coach.resolve_multiplexer_mode is not implemented"

    result = fn(explicit_flag=None, env={})
    assert result == "surface", (
        f"without mux env vars, default must be 'surface' (E007); got {result!r}"
    )
