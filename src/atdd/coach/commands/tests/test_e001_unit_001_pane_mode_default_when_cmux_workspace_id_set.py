# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:E001-UNIT-001-pane-mode-default-when-cmux-workspace-id-set
# Acceptance: acc:dispatch-ux-defaults-and-primer:E001-UNIT-001-pane-mode-default-when-cmux-workspace-id-set
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E001
# Phase: GREEN
# Layer: application
# Runtime: python
"""E001-UNIT-001 — resolve_multiplexer_mode returns 'surface' (not 'pane') in all cases.

GREEN: E007 (#830) superseded E001's 'pane' fix — cmux new-pane is also
deprecated (Broken pipe on cmux >=0.64.7). The function now unconditionally
returns 'surface' when no explicit flag is given, regardless of env vars.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_surface_mode_when_cmux_workspace_id_set():
    """resolve_multiplexer_mode returns 'surface' when CMUX_WORKSPACE_ID set."""
    from atdd.coach.commands import coach

    fn = getattr(coach, "resolve_multiplexer_mode", None)
    assert fn is not None, "coach.resolve_multiplexer_mode is not implemented"

    result = fn(explicit_flag=None, env={"CMUX_WORKSPACE_ID": "workspace:1"})
    assert result == "surface", (
        f"expected 'surface' when CMUX_WORKSPACE_ID is set (E007), got {result!r}"
    )


def test_explicit_flag_wins_over_env():
    """An explicit --multiplexer-mode='surface' overrides env vars."""
    from atdd.coach.commands import coach

    fn = getattr(coach, "resolve_multiplexer_mode", None)
    assert fn is not None, "coach.resolve_multiplexer_mode is not implemented"

    result = fn(
        explicit_flag="surface",
        env={"CMUX_WORKSPACE_ID": "workspace:1"},
    )
    assert result == "surface", (
        f"explicit_flag='surface' must override env var; got {result!r}"
    )


def test_surface_default_when_no_mux_env():
    """Without any mux env var, 'surface' is the default (E007: workspace/pane both deprecated)."""
    from atdd.coach.commands import coach

    fn = getattr(coach, "resolve_multiplexer_mode", None)
    assert fn is not None, "coach.resolve_multiplexer_mode is not implemented"

    result = fn(explicit_flag=None, env={})
    assert result == "surface", (
        f"without any mux env var, default must be 'surface'; got {result!r}"
    )
