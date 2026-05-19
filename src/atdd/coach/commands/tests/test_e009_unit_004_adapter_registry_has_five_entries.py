# URN: acc:spawn-agents:E009-UNIT-004-adapter-registry-has-five-entries
"""RED test: ADAPTER_REGISTRY contains exactly 5 entries after the change."""
from __future__ import annotations


def test_adapter_registry_has_five_entries():
    from atdd.coach.commands.spawn import ADAPTER_REGISTRY

    assert set(ADAPTER_REGISTRY.keys()) == {
        "claude-code",
        "claude-glm",
        "claude-gpt",
        "codex",
        "gemini",
    }


def test_all_adapter_values_are_callable():
    from atdd.coach.commands.spawn import ADAPTER_REGISTRY

    for name, fn in ADAPTER_REGISTRY.items():
        assert callable(fn), f"ADAPTER_REGISTRY[{name!r}] is not callable"
