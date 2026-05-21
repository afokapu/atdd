# URN: test:spawn-agents:spawn-time-non-interactive-convention:E013-UNIT-001-adapter-registry-entries-have-permission-fields
# Acceptance: acc:spawn-agents:E013-UNIT-001-adapter-registry-entries-have-permission-fields
"""E013-UNIT-001 — ADAPTER_REGISTRY carries permission_flags and allowed_tools on every entry.

RED: ADAPTER_REGISTRY is currently dict[str, Callable[[Path], str]]; accessing
.permission_flags or .allowed_tools will fail (AttributeError or missing key).
GREEN: Refactor to AdapterConfig dataclass so each entry carries structured fields.
"""
import pytest
from atdd.coach.commands.spawn import ADAPTER_REGISTRY


EXPECTED_ADAPTERS = ["claude-code", "claude-glm", "claude-gpt", "codex", "gemini"]


def test_all_expected_adapters_are_registered():
    for key in EXPECTED_ADAPTERS:
        assert key in ADAPTER_REGISTRY, f"Adapter {key!r} missing from ADAPTER_REGISTRY"


def test_every_adapter_has_permission_flags():
    for key, entry in ADAPTER_REGISTRY.items():
        flags = getattr(entry, "permission_flags", None)
        assert flags is not None, (
            f"ADAPTER_REGISTRY[{key!r}] missing permission_flags attribute. "
            "E013: each entry must carry structured permission_flags (list[str])."
        )
        assert isinstance(flags, list), (
            f"ADAPTER_REGISTRY[{key!r}].permission_flags must be list[str], got {type(flags)}"
        )
        assert len(flags) > 0, (
            f"ADAPTER_REGISTRY[{key!r}].permission_flags is empty — at least one flag required."
        )


def test_every_adapter_has_allowed_tools():
    for key, entry in ADAPTER_REGISTRY.items():
        tools = getattr(entry, "allowed_tools", None)
        assert tools is not None, (
            f"ADAPTER_REGISTRY[{key!r}] missing allowed_tools attribute. "
            "E013: each entry must carry structured allowed_tools (list[str])."
        )
        assert isinstance(tools, list), (
            f"ADAPTER_REGISTRY[{key!r}].allowed_tools must be list[str], got {type(tools)}"
        )
        assert len(tools) > 0, (
            f"ADAPTER_REGISTRY[{key!r}].allowed_tools is empty — at least one tool required."
        )
