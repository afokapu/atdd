# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E014-UNIT-003-claude-code-adapter-never-emits-forbidden-flag
# Acceptance: acc:govern-lifecycle:E014-UNIT-003-claude-code-adapter-never-emits-forbidden-flag
# WMBT: wmbt:govern-lifecycle:E014
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""acc:govern-lifecycle:E014-UNIT-003 — _claude_code_adapter never emits --dangerously-skip-permissions."""
from __future__ import annotations


def test_claude_code_adapter_never_emits_forbidden_flag(tmp_path):
    from atdd.coach.commands.spawn import _claude_code_adapter

    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("# test prompt")

    command = _claude_code_adapter(prompt_path=prompt_path)

    assert "--dangerously-skip-permissions" not in command, (
        f"_claude_code_adapter must not emit --dangerously-skip-permissions, got: {command!r}"
    )
    assert "bypassPermissions" not in command, (
        f"_claude_code_adapter must not emit bypassPermissions, got: {command!r}"
    )
