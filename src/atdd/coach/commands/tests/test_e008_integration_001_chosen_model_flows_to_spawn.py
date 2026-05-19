# URN: test:spawn-agents:interactive-model-selection-at-spawn:E008-INTEGRATION-001-chosen-model-flows-to-spawn
# Acceptance: acc:spawn-agents:E008-INTEGRATION-001-chosen-model-flows-to-spawn
# WMBT: wmbt:spawn-agents:E008
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E008-INTEGRATION-001 — a model chosen via the interactive prompt flows
through run_cli() and is passed to run() as persona_llm.

RED: run_cli() does not call prompt_persona_models() yet — there is no
TTY-gate in the coach dispatch path. This test pins that when stdin is a TTY,
--persona-llm is absent, and --no-prompt is absent, run_cli() resolves the
model via the prompt and forwards the chosen persona_llm to run().
"""
from __future__ import annotations

import io
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.platform]


def test_run_cli_forwards_prompt_result_to_run(monkeypatch):
    """When run_cli() detects a TTY with no --persona-llm, it calls
    prompt_persona_models() and passes its result to run() as persona_llm."""
    import atdd.coach.commands.coach as coach_mod

    captured_kwargs: dict = {}

    def fake_run(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return 0

    # Fake stdin that types 'claude-code' for every persona.
    from atdd.coach.commands.spawn import PERSONAS

    stdin_lines = "\n".join(["claude-code"] * len(PERSONAS)) + "\n"
    fake_stdin = io.StringIO(stdin_lines)

    monkeypatch.setattr(coach_mod, "run", fake_run)
    monkeypatch.setattr(
        "atdd.coach.commands.coach.ADAPTER_REGISTRY",
        {"claude-code": lambda p: "claude --dummy"},
        raising=False,
    )

    with (
        patch.object(coach_mod, "should_prompt_for_models", return_value=True),
        patch.object(
            coach_mod,
            "prompt_persona_models",
            wraps=lambda personas, known_models, stdin=None, stdout=None: {
                p: "claude-code" for p in personas
            },
        ) as mock_prompt,
    ):
        coach_mod.run_cli(["723"])

    # The prompt function must have been called.
    assert mock_prompt.called, (
        "prompt_persona_models() was never called — run_cli() did not invoke "
        "the interactive model prompt on a TTY with no --persona-llm"
    )

    # The persona_llm forwarded to run() must contain the prompt's choices.
    forwarded = captured_kwargs.get("persona_llm", {})
    assert forwarded, (
        f"run() received empty persona_llm — the prompt result was not forwarded: "
        f"{captured_kwargs!r}"
    )
    for persona in PERSONAS:
        assert persona in forwarded, (
            f"persona {persona!r} missing from forwarded persona_llm: {forwarded!r}"
        )
        assert forwarded[persona] == "claude-code", (
            f"persona {persona!r} mapped to {forwarded[persona]!r}, "
            f"expected 'claude-code'"
        )


def test_run_cli_no_prompt_flag_skips_prompt(monkeypatch):
    """When --no-prompt is given, run_cli() does not call prompt_persona_models()."""
    import atdd.coach.commands.coach as coach_mod

    monkeypatch.setattr(coach_mod, "run", lambda *a, **kw: 0)

    with patch.object(
        coach_mod, "prompt_persona_models"
    ) as mock_prompt:
        with patch.object(
            coach_mod, "should_prompt_for_models", return_value=False
        ):
            coach_mod.run_cli(["723", "--no-prompt"])

    assert not mock_prompt.called, (
        "prompt_persona_models() was called despite --no-prompt flag"
    )


def test_run_cli_persona_llm_flag_skips_prompt(monkeypatch):
    """When --persona-llm is given, run_cli() does not call prompt_persona_models()."""
    import atdd.coach.commands.coach as coach_mod

    monkeypatch.setattr(coach_mod, "run", lambda *a, **kw: 0)

    with patch.object(
        coach_mod, "prompt_persona_models"
    ) as mock_prompt:
        with patch.object(
            coach_mod, "should_prompt_for_models", return_value=False
        ):
            coach_mod.run_cli(["723", "--persona-llm", "tester=claude-code"])

    assert not mock_prompt.called, (
        "prompt_persona_models() was called despite --persona-llm being given"
    )
