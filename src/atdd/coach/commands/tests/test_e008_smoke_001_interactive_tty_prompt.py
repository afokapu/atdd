# URN: test:spawn-agents:interactive-model-selection-at-spawn:E008-SMOKE-001-interactive-tty-prompt-blocks-until-valid-input
# Acceptance: acc:spawn-agents:E008-SMOKE-001-interactive-tty-prompt-blocks-until-valid-input
# WMBT: wmbt:spawn-agents:E008
# Phase: SMOKE
# Layer: smoke
# Runtime: python
# Assertion: behavioral
"""E008-SMOKE-001 — the interactive model prompt resolves correctly under
conditions that mirror a real terminal session.

SMOKE: exercises the real `should_prompt_for_models` / `parse_cli` surface in
coach.py, so a non-TTY session and an explicit `--no-prompt` both suppress the
prompt rather than blocking on stdin.

#1486: this file also asserted that `prompt_persona_models` covered spawn's real
ADAPTER_REGISTRY / PERSONAS. Spawning left core and those production constants no
longer exist, so that assertion is retired; the prompt-suppression contract below
is unchanged and still runs against the live coach code.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.smoke]


def test_should_prompt_false_when_no_stdin_isatty():
    """should_prompt_for_models returns False when sys.stdin is not a TTY."""
    from atdd.coach.commands.coach import Config, should_prompt_for_models

    cfg = Config(issue_numbers=[723])
    # Non-TTY: isatty_fn always returns False.
    assert should_prompt_for_models(cfg, isatty_fn=lambda: False) is False


def test_no_prompt_flag_in_parse_cli_suppresses_prompt():
    """parse_cli(['723', '--no-prompt']) sets no_prompt=True and
    should_prompt_for_models returns False even for a TTY."""
    from atdd.coach.commands.coach import parse_cli, should_prompt_for_models

    cfg = parse_cli(["723", "--no-prompt"])
    assert cfg.no_prompt is True
    assert should_prompt_for_models(cfg, isatty_fn=lambda: True) is False
