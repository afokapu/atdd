# URN: test:spawn-agents:interactive-model-selection-at-spawn:E008-UNIT-005-invalid-model-rejected-with-valid-list
# Acceptance: acc:spawn-agents:E008-UNIT-005-invalid-model-rejected-with-valid-list
# WMBT: wmbt:spawn-agents:E008
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E008-UNIT-005 — an invalid model choice at the prompt is rejected and the
list of valid ids is shown; the user is re-prompted until a valid id is entered.

RED: ``prompt_persona_models`` does not exist yet. This test pins the
re-prompt loop and the rejection message format.
"""
from __future__ import annotations

import io

import pytest

pytestmark = [pytest.mark.platform]

KNOWN_MODELS = ["claude-code", "claude-sonnet"]


def test_invalid_then_valid_returns_valid():
    """An invalid id is rejected; the subsequent valid id is accepted."""
    from atdd.coach.commands.coach import prompt_persona_models

    # First input is invalid, second is valid.
    stdin_text = "not-a-model\nclaude-code\n"
    fake_stdin = io.StringIO(stdin_text)
    fake_stdout = io.StringIO()

    result = prompt_persona_models(
        ["planner"], KNOWN_MODELS, stdin=fake_stdin, stdout=fake_stdout
    )

    assert result["planner"] == "claude-code", (
        f"expected 'claude-code' after re-prompt, got {result['planner']!r}"
    )


def test_rejection_message_contains_invalid_id():
    """The rejection output mentions the invalid id the user typed."""
    from atdd.coach.commands.coach import prompt_persona_models

    invalid = "not-a-model"
    stdin_text = f"{invalid}\nclaude-code\n"
    fake_stdin = io.StringIO(stdin_text)
    fake_stdout = io.StringIO()

    prompt_persona_models(
        ["planner"], KNOWN_MODELS, stdin=fake_stdin, stdout=fake_stdout
    )

    output = fake_stdout.getvalue()
    assert invalid in output, (
        f"rejection message does not mention invalid id {invalid!r}: {output!r}"
    )


def test_rejection_message_contains_valid_ids():
    """The rejection output lists the valid model ids."""
    from atdd.coach.commands.coach import prompt_persona_models

    stdin_text = "bad-id\nclaude-sonnet\n"
    fake_stdin = io.StringIO(stdin_text)
    fake_stdout = io.StringIO()

    prompt_persona_models(
        ["tester"], KNOWN_MODELS, stdin=fake_stdin, stdout=fake_stdout
    )

    output = fake_stdout.getvalue()
    for valid_id in KNOWN_MODELS:
        assert valid_id in output, (
            f"valid model id {valid_id!r} not listed in rejection message: {output!r}"
        )


def test_result_does_not_contain_invalid_model():
    """The returned dict never maps a persona to an invalid model id."""
    from atdd.coach.commands.coach import prompt_persona_models

    stdin_text = "invalid-model\nclaude-code\n"
    fake_stdin = io.StringIO(stdin_text)
    fake_stdout = io.StringIO()

    result = prompt_persona_models(
        ["reviewer"], KNOWN_MODELS, stdin=fake_stdin, stdout=fake_stdout
    )

    assert "invalid-model" not in result.values(), (
        f"invalid model appeared in result: {result!r}"
    )
