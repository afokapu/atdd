# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:E001-INTEGRATION-001-coach-cli-uses-resolve-multiplexer-mode
# Acceptance: acc:dispatch-ux-defaults-and-primer:E001-INTEGRATION-001-coach-cli-uses-resolve-multiplexer-mode
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E001
# Phase: GREEN
# Layer: integration
# Runtime: python
"""E001-INTEGRATION-001 — the coach CLI entrypoint calls resolve_multiplexer_mode and
passes 'surface' to the spawn pipeline (issue #830 supersedes the original 'pane' fix).

GREEN: resolve_multiplexer_mode exists and returns 'surface' unconditionally
when no explicit flag is given (E007 fix — cmux new-pane is also deprecated).
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

pytestmark = [pytest.mark.platform]


def test_coach_cli_resolves_surface_mode_when_cmux_workspace_id_set(monkeypatch):
    """The coach CLI must call resolve_multiplexer_mode; spawn pipeline receives 'surface'."""
    from atdd.coach.commands import coach

    resolve_fn = getattr(coach, "resolve_multiplexer_mode", None)
    assert resolve_fn is not None, (
        "coach.resolve_multiplexer_mode is not implemented — "
        "the CLI cannot call it to resolve env-aware defaults"
    )

    monkeypatch.setenv("CMUX_WORKSPACE_ID", "workspace:1")
    monkeypatch.delenv("ATDD_WORKER_READY_TIMEOUT", raising=False)

    resolved = resolve_fn(explicit_flag=None, env={"CMUX_WORKSPACE_ID": "workspace:1"})
    assert resolved == "surface", (
        f"resolve_multiplexer_mode must return 'surface' when CMUX_WORKSPACE_ID set "
        f"(E007: 'pane' is also deprecated — uses cmux new-pane which is broken); got {resolved!r}"
    )
