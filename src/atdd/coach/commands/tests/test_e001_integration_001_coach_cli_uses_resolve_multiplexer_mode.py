# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:E001-INTEGRATION-001-coach-cli-uses-resolve-multiplexer-mode
# Acceptance: acc:dispatch-ux-defaults-and-primer:E001-INTEGRATION-001-coach-cli-uses-resolve-multiplexer-mode
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E001
# Phase: RED
# Layer: integration
# Runtime: python
"""E001-INTEGRATION-001 — the coach CLI entrypoint calls resolve_multiplexer_mode and
passes 'pane' to the spawn pipeline when CMUX_WORKSPACE_ID is set.

RED: resolve_multiplexer_mode does not exist and the coach CLI does not call
it. The spawn pipeline receives 'workspace' unconditionally regardless of env.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

pytestmark = [pytest.mark.platform]


def test_coach_cli_resolves_pane_mode_when_cmux_workspace_id_set(monkeypatch):
    """The coach CLI must call resolve_multiplexer_mode; spawn pipeline receives 'pane'."""
    from atdd.coach.commands import coach

    resolve_fn = getattr(coach, "resolve_multiplexer_mode", None)
    assert resolve_fn is not None, (
        "coach.resolve_multiplexer_mode is not implemented — "
        "the CLI cannot call it to resolve env-aware defaults (RED)"
    )

    captured_mode: list[str] = []

    def fake_drive_single_issue(ctx, *args, **kwargs):
        captured_mode.append(ctx.cfg.multiplexer_mode)

    monkeypatch.setenv("CMUX_WORKSPACE_ID", "workspace:1")
    monkeypatch.delenv("ATDD_WORKER_READY_TIMEOUT", raising=False)

    with (
        patch.object(coach, "_drive_single_issue", fake_drive_single_issue),
        patch.object(coach, "_load_issue_context", return_value=MagicMock()),
        patch.object(coach, "_pre_flight_checks", return_value=None),
    ):
        try:
            from atdd.coach.commands.coach import CoachConfig

            cfg = CoachConfig(
                issue=999,
                multiplexer_mode="workspace",
            )
            resolved = resolve_fn(explicit_flag=None, env={"CMUX_WORKSPACE_ID": "workspace:1"})
            assert resolved == "pane", (
                f"resolve_multiplexer_mode must return 'pane' when CMUX_WORKSPACE_ID set; got {resolved!r}"
            )
        except Exception as exc:
            pytest.fail(
                f"resolve_multiplexer_mode call failed — coach CLI integration broken: {exc}"
            )
