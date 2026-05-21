# URN: test:spawn-agents:spawn-time-non-interactive-convention:E013-UNIT-002-claude-adapters-declare-accept-edits-flag
# Acceptance: acc:spawn-agents:E013-UNIT-002-claude-adapters-declare-accept-edits-flag
"""E013-UNIT-002 — claude-code, claude-glm, claude-gpt declare --permission-mode acceptEdits.

RED: permission_flags are embedded inline in the shell command string; there is no
structured field to introspect.
GREEN: AdapterConfig.permission_flags carries the flags as a list; joining them yields
'--permission-mode acceptEdits'.
"""
import pytest
from atdd.coach.commands.spawn import ADAPTER_REGISTRY

CLAUDE_ADAPTERS = ["claude-code", "claude-glm", "claude-gpt"]


@pytest.mark.parametrize("adapter_key", CLAUDE_ADAPTERS)
def test_claude_adapter_has_accept_edits_in_permission_flags(adapter_key):
    entry = ADAPTER_REGISTRY[adapter_key]
    flags_str = " ".join(getattr(entry, "permission_flags", []))
    assert "--permission-mode" in flags_str, (
        f"ADAPTER_REGISTRY[{adapter_key!r}].permission_flags does not contain '--permission-mode'. "
        "E013: claude adapters must declare --permission-mode as a structured flag."
    )
    assert "acceptEdits" in flags_str, (
        f"ADAPTER_REGISTRY[{adapter_key!r}].permission_flags does not contain 'acceptEdits'. "
        "E013: the canonical non-interactive flag is '--permission-mode acceptEdits'."
    )


@pytest.mark.parametrize("adapter_key", list(ADAPTER_REGISTRY.keys()))
def test_no_adapter_declares_dangerously_skip_permissions(adapter_key):
    entry = ADAPTER_REGISTRY[adapter_key]
    flags_str = " ".join(getattr(entry, "permission_flags", []))
    assert "--dangerously-skip-permissions" not in flags_str, (
        f"ADAPTER_REGISTRY[{adapter_key!r}].permission_flags contains forbidden flag "
        "'--dangerously-skip-permissions'. Use '--permission-mode acceptEdits' instead (E013)."
    )


@pytest.mark.parametrize("adapter_key", list(ADAPTER_REGISTRY.keys()))
def test_no_adapter_declares_permission_mode_ask(adapter_key):
    entry = ADAPTER_REGISTRY[adapter_key]
    flags_str = " ".join(getattr(entry, "permission_flags", []))
    combined = flags_str
    assert "--permission-mode ask" not in combined, (
        f"ADAPTER_REGISTRY[{adapter_key!r}].permission_flags contains '--permission-mode ask' "
        "which causes interactive modals. Use 'acceptEdits' instead (E013)."
    )
