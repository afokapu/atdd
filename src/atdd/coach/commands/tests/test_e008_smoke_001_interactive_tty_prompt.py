# URN: test:spawn-agents:interactive-model-selection-at-spawn:E008-SMOKE-001-interactive-tty-prompt-blocks-until-valid-input
# Acceptance: acc:spawn-agents:E008-SMOKE-001-interactive-tty-prompt-blocks-until-valid-input
# WMBT: wmbt:spawn-agents:E008
# Phase: SMOKE
# Layer: smoke
# Runtime: python
# Assertion: behavioral
"""E008-SMOKE-001 — the interactive prompt resolves correctly under conditions
that mirror a real terminal session: ADAPTER_REGISTRY reflects reality and
all PERSONAS are covered exactly once.

SMOKE: validates prompt_persona_models against the real ADAPTER_REGISTRY and
PERSONAS from spawn.py, ensuring production constants are used and no persona
is skipped or duplicated.
"""
from __future__ import annotations

import io

import pytest

pytestmark = [pytest.mark.smoke]


def test_prompt_covers_all_real_personas():
    """prompt_persona_models accepts exactly one input per real PERSONAS entry."""
    from atdd.coach.commands.coach import prompt_persona_models
    from atdd.coach.commands.spawn import ADAPTER_REGISTRY, PERSONAS

    known = sorted(ADAPTER_REGISTRY)
    # Must have at least 'claude-code' in the real registry.
    assert "claude-code" in known, (
        f"ADAPTER_REGISTRY missing 'claude-code': {known}"
    )

    # Operator types 'claude-code' for every persona.
    stdin_text = "\n".join(["claude-code"] * len(PERSONAS)) + "\n"
    fake_stdin = io.StringIO(stdin_text)
    fake_stdout = io.StringIO()

    result = prompt_persona_models(
        PERSONAS, known, stdin=fake_stdin, stdout=fake_stdout
    )

    assert set(result.keys()) == set(PERSONAS), (
        f"prompt result covers {sorted(result)} but PERSONAS is {sorted(PERSONAS)}"
    )
    for persona, model in result.items():
        assert model in known, (
            f"persona {persona!r} resolved to unknown model {model!r}"
        )


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
