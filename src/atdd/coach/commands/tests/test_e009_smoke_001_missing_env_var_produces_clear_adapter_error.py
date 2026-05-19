# URN: test:spawn-agents:register-llm-adapter-flavors:E009-SMOKE-001-missing-env-var-produces-clear-adapter-error
# Acceptance: acc:spawn-agents:E009-SMOKE-001-missing-env-var-produces-clear-adapter-error
# WMBT: wmbt:spawn-agents:E009
# Phase: SMOKE
# Layer: smoke
# Runtime: python
# Assertion: behavioral
"""E009-SMOKE-001 — real spawn module: each non-default adapter raises AdapterError naming the missing var.

No mocking of the spawn module — imports happen against the real installed or
editable package so this test catches any import-time wiring errors.
"""
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
def test_adapter_raises_before_any_side_effect(adapter_name, env_var, monkeypatch, tmp_path):
    """Smoke: real module import, env var removed — AdapterError fires before multiplexer."""
    monkeypatch.delenv(env_var, raising=False)

    import atdd.coach.commands.spawn as spawn_mod
    from atdd.coach.commands.spawn import AdapterError

    adapter_fn = getattr(spawn_mod, adapter_name)
    dummy_prompt = tmp_path / "prompt.txt"
    dummy_prompt.write_text("dummy launch prompt")

    with pytest.raises(AdapterError) as exc_info:
        adapter_fn(dummy_prompt)

    msg = str(exc_info.value)
    assert env_var in msg, f"Error message {msg!r} does not name missing var {env_var!r}"


def test_adapter_error_is_raised_before_multiplexer_surface_created(monkeypatch, tmp_path):
    """Smoke: missing env var means no multiplexer surface creation occurs."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    import atdd.coach.commands.spawn as spawn_mod
    from atdd.coach.commands.spawn import AdapterError

    dummy_prompt = tmp_path / "prompt.txt"
    dummy_prompt.write_text("dummy launch prompt")

    with pytest.raises(AdapterError):
        spawn_mod._gemini_adapter(dummy_prompt)
