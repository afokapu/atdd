# URN: test:spawn-agents:interactive-model-selection-at-spawn:E008-UNIT-004-no-prompt-flag-skips-prompt
# Acceptance: acc:spawn-agents:E008-UNIT-004-no-prompt-flag-skips-prompt
# WMBT: wmbt:spawn-agents:E008
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E008-UNIT-004 — when --no-prompt is passed the interactive prompt is
suppressed even on a TTY.

RED: ``Config.no_prompt`` field and the ``--no-prompt`` CLI flag do not exist
yet; ``should_prompt_for_models`` does not exist either.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def _make_cfg_no_prompt():
    from atdd.coach.commands.coach import Config

    return Config(
        issue_numbers=[723],
        persona_llm={},
        no_prompt=True,
    )


def test_no_prompt_flag_returns_false_on_tty():
    """should_prompt_for_models returns False when --no-prompt is set."""
    from atdd.coach.commands.coach import should_prompt_for_models

    cfg = _make_cfg_no_prompt()
    assert should_prompt_for_models(cfg, isatty_fn=lambda: True) is False


def test_parse_cli_no_prompt_flag():
    """parse_cli parses --no-prompt and sets no_prompt=True on Config."""
    from atdd.coach.commands.coach import parse_cli

    cfg = parse_cli(["723", "--no-prompt"])
    assert cfg.no_prompt is True


def test_parse_cli_no_prompt_defaults_false():
    """parse_cli sets no_prompt=False when --no-prompt is absent."""
    from atdd.coach.commands.coach import parse_cli

    cfg = parse_cli(["723"])
    assert cfg.no_prompt is False
