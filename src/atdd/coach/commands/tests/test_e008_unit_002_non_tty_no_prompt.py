# URN: test:spawn-agents:interactive-model-selection-at-spawn:E008-UNIT-002-non-tty-no-prompt
# Acceptance: acc:spawn-agents:E008-UNIT-002-non-tty-no-prompt
# WMBT: wmbt:spawn-agents:E008
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E008-UNIT-002 — when stdin is not a TTY the interactive prompt is skipped
entirely; should_prompt_for_models() returns False.

RED: ``should_prompt_for_models`` does not exist in coach.py yet.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def _make_cfg(persona_llm=None, no_prompt=False):
    from atdd.coach.commands.coach import Config

    return Config(
        issue_numbers=[723],
        persona_llm=persona_llm or {},
        no_prompt=no_prompt,
    )


def test_non_tty_returns_false():
    """should_prompt_for_models returns False when isatty_fn() is False."""
    from atdd.coach.commands.coach import should_prompt_for_models

    cfg = _make_cfg()
    assert should_prompt_for_models(cfg, isatty_fn=lambda: False) is False


def test_tty_with_empty_persona_llm_returns_true():
    """Returns True when TTY, no --persona-llm, and no --no-prompt."""
    from atdd.coach.commands.coach import should_prompt_for_models

    cfg = _make_cfg()
    assert should_prompt_for_models(cfg, isatty_fn=lambda: True) is True
