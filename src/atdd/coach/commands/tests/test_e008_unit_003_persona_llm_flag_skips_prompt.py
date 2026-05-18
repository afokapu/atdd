# URN: test:spawn-agents:interactive-model-selection-at-spawn:E008-UNIT-003-persona-llm-flag-skips-prompt
# Acceptance: acc:spawn-agents:E008-UNIT-003-persona-llm-flag-skips-prompt
# WMBT: wmbt:spawn-agents:E008
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E008-UNIT-003 — when --persona-llm is given the interactive prompt is
skipped even on a TTY.

RED: ``should_prompt_for_models`` does not exist in coach.py yet.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def _make_cfg_with_persona_llm():
    from atdd.coach.commands.coach import Config

    return Config(
        issue_numbers=[723],
        persona_llm={"tester": "claude-code", "coder": "claude-code"},
        no_prompt=False,
    )


def test_persona_llm_given_returns_false_on_tty():
    """should_prompt_for_models returns False when --persona-llm is already set."""
    from atdd.coach.commands.coach import should_prompt_for_models

    cfg = _make_cfg_with_persona_llm()
    assert should_prompt_for_models(cfg, isatty_fn=lambda: True) is False


def test_parse_cli_persona_llm_populates_config():
    """parse_cli honours --persona-llm and sets persona_llm dict on Config."""
    from atdd.coach.commands.coach import parse_cli

    cfg = parse_cli(["723", "--persona-llm", "tester=claude-code,coder=claude-code"])
    assert cfg.persona_llm == {"tester": "claude-code", "coder": "claude-code"}
