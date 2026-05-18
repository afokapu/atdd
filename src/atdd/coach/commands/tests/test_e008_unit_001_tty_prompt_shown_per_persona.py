# URN: test:spawn-agents:interactive-model-selection-at-spawn:E008-UNIT-001-tty-prompt-shown-per-persona
# Acceptance: acc:spawn-agents:E008-UNIT-001-tty-prompt-shown-per-persona
# WMBT: wmbt:spawn-agents:E008
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E008-UNIT-001 — when stdin is a TTY, no --persona-llm is given, and
--no-prompt is absent, prompt_persona_models() emits one prompt per persona
and returns the chosen models.

RED: ``prompt_persona_models`` does not exist in coach.py yet. This test
imports and calls it, pinning the contract: one stdin readline per persona,
a dict with every persona mapped to the chosen model, and stdout output
containing each persona name.
"""
from __future__ import annotations

import io

import pytest

pytestmark = [pytest.mark.platform]

KNOWN_MODELS = ["claude-code", "claude-sonnet"]
PERSONAS = ["planner", "tester", "coder", "reviewer"]


def test_prompt_returns_all_personas_mapped(monkeypatch):
    """prompt_persona_models returns a dict mapping every persona to the
    model typed by the operator."""
    from atdd.coach.commands.coach import prompt_persona_models

    # operator types the same valid model for every persona
    stdin_text = "\n".join(["claude-code"] * len(PERSONAS)) + "\n"
    fake_stdin = io.StringIO(stdin_text)
    fake_stdout = io.StringIO()

    result = prompt_persona_models(
        PERSONAS, KNOWN_MODELS, stdin=fake_stdin, stdout=fake_stdout
    )

    assert set(result.keys()) == set(PERSONAS), (
        f"expected all personas {PERSONAS!r} in result, got {sorted(result)}"
    )
    for persona, model in result.items():
        assert model == "claude-code", (
            f"persona {persona!r} mapped to {model!r}, expected 'claude-code'"
        )


def test_prompt_stdout_mentions_each_persona():
    """The captured stdout contains at least one mention of each persona."""
    from atdd.coach.commands.coach import prompt_persona_models

    stdin_text = "\n".join(["claude-code"] * len(PERSONAS)) + "\n"
    fake_stdin = io.StringIO(stdin_text)
    fake_stdout = io.StringIO()

    prompt_persona_models(
        PERSONAS, KNOWN_MODELS, stdin=fake_stdin, stdout=fake_stdout
    )

    output = fake_stdout.getvalue()
    for persona in PERSONAS:
        assert persona in output, (
            f"persona {persona!r} not mentioned in prompt output: {output!r}"
        )


def test_prompt_distinct_choices_per_persona():
    """Different personas can receive different model choices."""
    from atdd.coach.commands.coach import prompt_persona_models

    two_personas = ["planner", "coder"]
    # planner → claude-code, coder → claude-sonnet
    stdin_text = "claude-code\nclaude-sonnet\n"
    fake_stdin = io.StringIO(stdin_text)
    fake_stdout = io.StringIO()

    result = prompt_persona_models(
        two_personas, KNOWN_MODELS, stdin=fake_stdin, stdout=fake_stdout
    )

    assert result["planner"] == "claude-code"
    assert result["coder"] == "claude-sonnet"
