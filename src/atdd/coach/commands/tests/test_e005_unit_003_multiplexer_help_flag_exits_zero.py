# URN: test:dispatch-ux-defaults-and-primer:multiplexer-primer:E005-UNIT-003-multiplexer-help-flag-exits-zero
# Acceptance: acc:dispatch-ux-defaults-and-primer:E005-UNIT-003-multiplexer-help-flag-exits-zero
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E005
# Phase: RED
# Layer: presentation
# Runtime: python
"""E005-UNIT-003 — atdd coach --multiplexer-help prints primer and exits 0 without running coach.

RED: --multiplexer-help does not exist as a coach CLI flag. There is no way to
display the primer outside of a full coach dispatch invocation.
"""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.platform]


def test_multiplexer_help_flag_exists_in_parser():
    """The atdd coach CLI parser must expose a --multiplexer-help argument."""
    from atdd.coach.commands import coach

    make_parser = getattr(coach, "_make_coach_parser", None) or getattr(
        coach, "make_parser", None
    )
    if make_parser is None:
        # Try importing the parser directly.
        try:
            from atdd.coach.commands.coach import _make_coach_parser as make_parser  # type: ignore[attr-defined]
        except ImportError:
            pytest.fail(
                "cannot find _make_coach_parser in atdd.coach.commands.coach — "
                "--multiplexer-help flag cannot be verified (RED)"
            )

    parser = make_parser()
    option_strings = {
        opt
        for action in parser._actions
        for opt in (action.option_strings or [])
    }
    assert "--multiplexer-help" in option_strings, (
        f"--multiplexer-help is not in the coach CLI parser; "
        f"available flags: {sorted(option_strings)}"
    )


def test_multiplexer_help_exits_zero_without_running_pipeline(tmp_path, monkeypatch):
    """atdd coach --multiplexer-help exits 0 and does not invoke the coach pipeline."""
    from atdd.coach.commands import coach

    make_parser = getattr(coach, "_make_coach_parser", None)
    assert make_parser is not None, (
        "_make_coach_parser not found — cannot test --multiplexer-help exit (RED)"
    )

    pipeline_called = []

    def fake_pipeline(*args, **kwargs):
        pipeline_called.append(True)

    with patch.object(coach, "_drive_single_issue", fake_pipeline):
        with pytest.raises(SystemExit) as exc_info:
            parser = make_parser()
            ns = parser.parse_args(["--multiplexer-help"])
            # If --multiplexer-help triggers immediate exit, this is caught above.
            # Otherwise the CLI main must handle it before calling the pipeline.
            handle_fn = getattr(coach, "_handle_multiplexer_help", None)
            if handle_fn:
                handle_fn(ns, env={"CMUX_WORKSPACE_ID": "workspace:1"})
            else:
                pytest.fail(
                    "_handle_multiplexer_help not found — "
                    "--multiplexer-help exit logic is not implemented (RED)"
                )

    assert exc_info.value.code == 0, (
        f"--multiplexer-help must exit 0; got {exc_info.value.code!r}"
    )
    assert not pipeline_called, (
        "--multiplexer-help must NOT invoke the coach pipeline"
    )
