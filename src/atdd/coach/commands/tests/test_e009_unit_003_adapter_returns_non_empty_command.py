# URN: acc:spawn-agents:E009-UNIT-003-each-adapter-returns-non-empty-command-with-prompt-path
"""RED test: each adapter returns a non-empty command string when credentials are present."""
from __future__ import annotations

import pytest
from pathlib import Path


@pytest.mark.parametrize(
    "adapter_name,env_var,env_val",
    [
        ("_claude_glm_adapter", "Z_AI_API_KEY", "fake-z-key"),
        ("_claude_gpt_adapter", "OPENROUTER_API_KEY", "fake-or-key"),
        ("_codex_adapter", "OPENAI_API_KEY", "fake-oai-key"),
        ("_gemini_adapter", "GOOGLE_API_KEY", "fake-goog-key"),
    ],
)
def test_adapter_returns_non_empty_command(adapter_name, env_var, env_val, monkeypatch, tmp_path):
    monkeypatch.setenv(env_var, env_val)
    import atdd.coach.commands.spawn as spawn_mod

    adapter_fn = getattr(spawn_mod, adapter_name)
    dummy_prompt = tmp_path / "prompt.txt"
    dummy_prompt.write_text("test prompt")

    result = adapter_fn(dummy_prompt)

    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.parametrize(
    "adapter_name,env_var,env_val",
    [
        ("_codex_adapter", "OPENAI_API_KEY", "fake-oai-key"),
        ("_gemini_adapter", "GOOGLE_API_KEY", "fake-goog-key"),
    ],
)
def test_adapter_contains_prompt_path(adapter_name, env_var, env_val, monkeypatch, tmp_path):
    monkeypatch.setenv(env_var, env_val)
    import atdd.coach.commands.spawn as spawn_mod

    adapter_fn = getattr(spawn_mod, adapter_name)
    dummy_prompt = tmp_path / "prompt.txt"
    dummy_prompt.write_text("test prompt")

    result = adapter_fn(dummy_prompt)

    assert str(dummy_prompt) in result
