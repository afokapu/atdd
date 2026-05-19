# URN: acc:spawn-agents:E009-INTEGRATION-001-spawn-cli-resolves-new-adapter-ids
"""RED test: cmd_spawn resolves all four new adapter ids without error when credentials are present."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


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

    fake_mux = MagicMock()
    fake_mux.new_workspace.return_value = "ws-001"
    fake_mux.new_surface.return_value = "surface-001"

    from atdd.coach.commands.spawn import cmd_spawn, AdapterError

    args = [
        "--persona", "coder",
        "--llm", llm_id,
        "--worktree", str(worktree),
        "--issue", "699",
        "--agent-id", f"coder-699-001",
        "--runtime", str(runtime),
    ]

    with patch("atdd.coach.commands.spawn._resolve_multiplexer", return_value=fake_mux):
        try:
            cmd_spawn(args)
        except AdapterError:
            pytest.fail(f"AdapterError raised for {llm_id} with env var {env_var} set")
        except SystemExit as e:
            if e.code not in (0, None):
                pytest.fail(f"cmd_spawn exited with code {e.code} for {llm_id}")


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
