# URN: test:mediate-worker-decisions:surface-worker-decisions:Y002-INTEGRATION-001-spawn-adapter-command-realizes-policy
# Acceptance: acc:mediate-worker-decisions:Y002-INTEGRATION-001-spawn-adapter-command-realizes-policy
# WMBT: wmbt:mediate-worker-decisions:Y002
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""Y002-INTEGRATION-001 — the production spawn adapter realizes the policy.

The cmux-surface spawn adapter (ADAPTER_REGISTRY in atdd.coach.commands.spawn) is
the consumer that loads the surfacing values into the launch command. This pins it
to the declared policy WITHOUT a live worker: the rendered ``--allowedTools`` equals
the resolved ``allowed_tools`` (Bash absent), ``--permission-mode`` equals the
resolved mode, and no forbidden bypass flag appears — so the leash cannot creep back
in (the #967 regression) on either launch transport.
"""
from __future__ import annotations

import shlex
from pathlib import Path

from atdd.mediate_worker_decisions.surface_worker_decisions.src.application.resolve_surfacing_values import (
    resolve,
)
from atdd.mediate_worker_decisions.surface_worker_decisions.src.domain.decision_surfacing_policy import (
    FORBIDDEN_FLAGS,
)

_CLAUDE_ADAPTERS = ("claude-code", "claude-glm", "claude-gpt")


def _allowed_tools_from_command(command: str) -> list[str]:
    """Extract the --allowedTools value (a comma-joined token list) from a
    rendered claude launch command — comma-delimited so scoped multi-word Bash
    patterns (e.g. ``Bash(atdd validate:*)``) survive as single entries (E031 #1062)."""
    tokens = shlex.split(command)
    idx = tokens.index("--allowedTools")
    return tokens[idx + 1].split(",")


def _set_required_env(monkeypatch) -> None:
    """The glm/gpt adapters fail loud without their credential env vars."""
    monkeypatch.setenv("Z_AI_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def test_every_claude_adapter_command_realizes_resolved_policy(tmp_path, monkeypatch):
    from atdd.coach.commands.spawn import ADAPTER_REGISTRY

    _set_required_env(monkeypatch)
    prompt_path = tmp_path / ".launch_prompt.txt"
    prompt_path.write_text("body")

    for kind in _CLAUDE_ADAPTERS:
        command = ADAPTER_REGISTRY[kind](prompt_path)
        values = resolve(kind)

        rendered_tools = _allowed_tools_from_command(command)
        # The rendered allowedTools is the EXACT image of the resolved policy.
        assert rendered_tools == list(values.allowed_tools), kind
        # Bare ``Bash`` (the broad class) is never pre-authorized — it must surface
        # to the Feed; only scoped ``Bash(<cmd>:*)`` safe prefixes are allowed (#1062).
        assert "Bash" not in rendered_tools, kind
        # permission-mode is the policy mode.
        assert f"--permission-mode {values.permission_mode}" in command, kind
        # No forbidden bypass flag may appear.
        for flag in FORBIDDEN_FLAGS:
            assert flag not in command, (kind, flag)
        assert "bypassPermissions" not in command, kind


def test_two_phase_commit_launcher_realizes_resolved_policy(monkeypatch):
    """The second launch transport (two_phase_commit) must render the same
    policy image, so no transport reintroduces the freedom-set bug (Y002)."""
    from atdd.coach.commands.spawn import _claude_surfacing_flags

    flags = _claude_surfacing_flags("claude-code")
    values = resolve("claude-code")

    launch_cmd = f"claude {flags}"
    rendered_tools = _allowed_tools_from_command(launch_cmd)
    assert rendered_tools == list(values.allowed_tools)
    assert "Bash" not in rendered_tools
    assert f"--permission-mode {values.permission_mode}" in launch_cmd
    assert "--dangerously-skip-permissions" not in launch_cmd
