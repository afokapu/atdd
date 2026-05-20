# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:E002-INTEGRATION-001-coach-cli-no-prompt-when-not-tty
# Acceptance: acc:dispatch-ux-defaults-and-primer:E002-INTEGRATION-001-coach-cli-no-prompt-when-not-tty
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E002
# Phase: RED
# Layer: integration
# Runtime: python
"""E002-INTEGRATION-001 — the coach CLI entrypoint calls resolve_no_prompt and
passes no_prompt=True to the spawn pipeline when stdin is not a TTY.

RED: resolve_no_prompt does not exist and the coach CLI does not call it.
sys.stdin.isatty() is never consulted at CoachConfig construction time, so
the no_prompt flag is always False (defaults) regardless of TTY state.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.platform]


def test_coach_cli_sets_no_prompt_when_stdin_not_tty(monkeypatch):
    """The coach CLI must call resolve_no_prompt; no_prompt=True when stdin not a TTY."""
    from atdd.coach.commands import coach

    resolve_fn = getattr(coach, "resolve_no_prompt", None)
    assert resolve_fn is not None, (
        "coach.resolve_no_prompt is not implemented — "
        "the CLI cannot auto-enable no-prompt for non-TTY contexts (RED)"
    )

    # Verify the helper works for the non-TTY case.
    result = resolve_fn(explicit_flag=None, isatty=False)
    assert result is True, (
        f"resolve_no_prompt must return True for isatty=False; got {result!r}"
    )

    # Verify the helper is wired into the CLI by checking that the CLI
    # argument parser calls resolve_no_prompt (or equivalent) when building
    # CoachConfig from namespace, with sys.stdin.isatty patched to False.
    calls: list[bool] = []
    original_resolve = resolve_fn

    def spy_resolve(explicit_flag, isatty):
        calls.append(isatty)
        return original_resolve(explicit_flag=explicit_flag, isatty=isatty)

    with patch.object(coach, "resolve_no_prompt", spy_resolve):
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            # Build a namespace as the CLI would (simulate argparse result).
            # This exercises the wiring path between argparse and CoachConfig.
            try:
                from atdd.coach.commands.coach import _build_coach_config_from_ns  # type: ignore[attr-defined]

                ns = type("NS", (), {"no_prompt": None, "issue": 999})()
                _build_coach_config_from_ns(ns)
                assert calls, (
                    "_build_coach_config_from_ns did not call resolve_no_prompt (RED)"
                )
            except (ImportError, AttributeError):
                pytest.fail(
                    "_build_coach_config_from_ns does not exist — resolve_no_prompt "
                    "is not wired into the CLI config-construction path (RED)"
                )
