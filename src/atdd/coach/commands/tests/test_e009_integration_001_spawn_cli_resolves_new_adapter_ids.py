# URN: test:spawn-agents:register-llm-adapter-flavors:E009-INTEGRATION-001-spawn-cli-resolves-new-adapter-ids
# Acceptance: acc:spawn-agents:E009-INTEGRATION-001-spawn-cli-resolves-new-adapter-ids
# WMBT: wmbt:spawn-agents:E009
# Phase: GREEN
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E009-INTEGRATION-001 — cmd_spawn resolves all four new adapter ids without error when credentials are present."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


class _FakeMux:
    """Minimal fake multiplexer that records calls without spawning real sessions."""

    def __init__(self):
        self.calls: list = []

    def new_workspace(self, name=None, **kw):
        self.calls.append(("new_workspace", name))
        return f"ws-{name}"

    def new_surface(self, name=None, workspace=None, command=None, **kw):
        self.calls.append(("new_surface", name, command))
        return f"surface-{name}"

    def paste_text(self, surface_ref, text, **kw):
        self.calls.append(("paste_text", surface_ref))

    def send_key(self, surface_ref, key, **kw):
        self.calls.append(("send_key", surface_ref, key))

    def list_surfaces(self, **kw):
        return []


@pytest.mark.parametrize(
    "llm_id,env_var,env_val",
    [
        ("claude-glm", "Z_AI_API_KEY", "fake-z-key"),
        ("claude-gpt", "OPENROUTER_API_KEY", "fake-or-key"),
        ("codex", "OPENAI_API_KEY", "fake-oai-key"),
        ("gemini", "GOOGLE_API_KEY", "fake-goog-key"),
    ],
)
def test_cmd_spawn_resolves_new_adapter(llm_id, env_var, env_val, monkeypatch, tmp_path):
    monkeypatch.setenv(env_var, env_val)

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    fake_mux = _FakeMux()

    import atdd.coach.commands.spawn as spawn_mod
    from atdd.coach.commands.spawn import AdapterError

    try:
        spawn_mod.cmd_spawn(
            persona="coder",
            llm=llm_id,
            worktree=worktree,
            issue=699,
            agent_id="coder-699-001",
            runtime_root=runtime,
            multiplexer=fake_mux,
        )
    except AdapterError:
        pytest.fail(f"AdapterError raised for {llm_id} with env var {env_var} set")


def test_new_adapters_produce_distinct_commands(monkeypatch, tmp_path):
    monkeypatch.setenv("Z_AI_API_KEY", "z-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("OPENAI_API_KEY", "oai-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "goog-key")

    import atdd.coach.commands.spawn as spawn_mod

    dummy_prompt = tmp_path / "prompt.txt"
    dummy_prompt.write_text("test")

    commands = {
        name: spawn_mod.ADAPTER_REGISTRY[name](dummy_prompt)
        for name in ("claude-glm", "claude-gpt", "codex", "gemini")
    }

    unique_commands = set(commands.values())
    assert len(unique_commands) == 4, (
        f"Expected 4 distinct adapter commands, got {len(unique_commands)}: {commands}"
    )
