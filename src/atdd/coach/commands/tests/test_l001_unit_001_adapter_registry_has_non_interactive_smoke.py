# URN: test:spawn-agents:spawn-time-non-interactive-convention:L001-UNIT-001-adapter-registry-has-non-interactive-smoke
# Acceptance: acc:spawn-agents:L001-UNIT-001-adapter-registry-has-non-interactive-smoke
"""L001-UNIT-001 — every ADAPTER_REGISTRY entry has a non_interactive_smoke callable.

RED: AdapterConfig does not exist yet; ADAPTER_REGISTRY entries have no such field.
GREEN: AdapterConfig.non_interactive_smoke is a callable (or None for adapters where
smoke is deferred); at minimum the field exists and is accessible.
"""
import pytest
from atdd.coach.commands.spawn import ADAPTER_REGISTRY


def test_every_adapter_has_non_interactive_smoke_attribute():
    for key, entry in ADAPTER_REGISTRY.items():
        assert hasattr(entry, "non_interactive_smoke"), (
            f"ADAPTER_REGISTRY[{key!r}] missing non_interactive_smoke attribute. "
            "L001: each AdapterConfig must declare a non_interactive_smoke field."
        )


def test_non_interactive_smoke_is_callable_or_none():
    for key, entry in ADAPTER_REGISTRY.items():
        smoke = entry.non_interactive_smoke
        assert smoke is None or callable(smoke), (
            f"ADAPTER_REGISTRY[{key!r}].non_interactive_smoke must be callable or None. "
            f"Got: {type(smoke)}"
        )
