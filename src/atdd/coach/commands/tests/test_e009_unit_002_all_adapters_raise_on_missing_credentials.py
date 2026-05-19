# URN: acc:spawn-agents:E009-UNIT-002-all-four-adapters-raise-on-missing-credentials
"""RED test: each of the four new adapters raises AdapterError when its env var is absent."""
from __future__ import annotations

import pytest
from pathlib import Path


@pytest.mark.parametrize(
    "adapter_name,env_var",
    [
        ("_claude_glm_adapter", "Z_AI_API_KEY"),
        ("_claude_gpt_adapter", "OPENROUTER_API_KEY"),
        ("_codex_adapter", "OPENAI_API_KEY"),
        ("_gemini_adapter", "GOOGLE_API_KEY"),
    ],
)
def test_adapter_raises_on_missing_env_var(adapter_name, env_var, monkeypatch, tmp_path):
    monkeypatch.delenv(env_var, raising=False)
    import atdd.coach.commands.spawn as spawn_mod
    from atdd.coach.commands.spawn import AdapterError

    adapter_fn = getattr(spawn_mod, adapter_name)
    dummy_prompt = tmp_path / "prompt.txt"
    dummy_prompt.write_text("test prompt")

    with pytest.raises(AdapterError) as exc_info:
        adapter_fn(dummy_prompt)

    assert env_var in str(exc_info.value)
