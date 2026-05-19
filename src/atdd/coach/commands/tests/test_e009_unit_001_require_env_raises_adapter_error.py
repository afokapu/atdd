# URN: test:spawn-agents:register-llm-adapter-flavors:E009-UNIT-001-require-env-raises-adapter-error-on-missing-var
# Acceptance: acc:spawn-agents:E009-UNIT-001-require-env-raises-adapter-error-on-missing-var
# WMBT: wmbt:spawn-agents:E009
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E009-UNIT-001 — _require_env raises AdapterError when env var is absent."""
from __future__ import annotations

import pytest


def test_require_env_raises_when_var_absent(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    from atdd.coach.commands.spawn import AdapterError, _require_env

    with pytest.raises(AdapterError) as exc_info:
        _require_env("GOOGLE_API_KEY", "gemini")

    msg = str(exc_info.value)
    assert "gemini" in msg
    assert "GOOGLE_API_KEY" in msg


def test_require_env_message_matches_pattern(monkeypatch):
    monkeypatch.delenv("Z_AI_API_KEY", raising=False)
    from atdd.coach.commands.spawn import AdapterError, _require_env

    with pytest.raises(AdapterError) as exc_info:
        _require_env("Z_AI_API_KEY", "claude-glm")

    assert str(exc_info.value) == "claude-glm: missing $Z_AI_API_KEY"


def test_require_env_succeeds_when_var_present(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from atdd.coach.commands.spawn import _require_env

    _require_env("OPENAI_API_KEY", "codex")
