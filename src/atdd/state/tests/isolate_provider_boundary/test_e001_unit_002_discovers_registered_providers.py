# URN: test:isolate-provider-boundary:register-sync-providers:E001-UNIT-002-discovers-registered-providers
# Acceptance: acc:isolate-provider-boundary:E001-UNIT-002-discovers-registered-providers
# WMBT: wmbt:isolate-provider-boundary:E001
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: register_provider() makes providers 'zeta' and 'alpha' discoverable by name, discovery returns them in deterministic name-sorted order regardless of registration order, and registering the same name twice is REFUSED rather than silently shadowed. Refs #1400.
"""Registration is deterministic, and a duplicate name is refused (E001-UNIT-002).

wagon: isolate-provider-boundary | feature: register-sync-providers | phase: GREEN
WMBT: wmbt:isolate-provider-boundary:E001

``zeta`` is registered first and ``alpha`` second, so insertion order and sorted order disagree —
which is the only way to find out which one discovery actually returns. Order matters because the
mirror's output must not depend on the order somebody happened to install two extensions in.

The refusal is the sharper half. Silently shadowing a duplicate name would mean the extensions
lock pins one provider's digest while the *other* one does the mirroring, and nothing anywhere
would ever notice — the lock would be verifying an extension that is not running.
"""
from __future__ import annotations

import pytest

from atdd.state import provider_seam
from atdd.state.provider_seam import ProviderRegistryError

from ._seam import StubProvider, factory


def test_e001_unit_002_discovers_registered_providers() -> None:
    """Both providers are discoverable, in name-sorted order — not registration order."""
    zeta = StubProvider(name="zeta")
    alpha = StubProvider(name="alpha")

    provider_seam.register_provider("zeta", factory(zeta))
    provider_seam.register_provider("alpha", factory(alpha))

    assert provider_seam.registered_names() == ["alpha", "zeta"]

    discovered = provider_seam.discover_providers()

    # Discoverable BY NAME...
    assert set(discovered) == {"alpha", "zeta"}
    assert discovered["alpha"] is alpha
    assert discovered["zeta"] is zeta

    # ...and in a deterministic, name-sorted order, though zeta was registered first.
    assert list(discovered) == ["alpha", "zeta"]
    assert list(provider_seam.discover_providers()) == ["alpha", "zeta"]


def test_e001_unit_002_a_duplicate_name_is_refused_not_shadowed() -> None:
    """Two providers cannot answer to one name: the second registration is refused."""
    first = StubProvider(name="github", body="v1")
    second = StubProvider(name="github", body="v2")

    provider_seam.register_provider("github", factory(first))

    with pytest.raises(ProviderRegistryError) as refusal:
        provider_seam.register_provider("github", factory(second))

    assert "already registered" in str(refusal.value)
    assert "shadow" in str(refusal.value)

    # The FIRST registration survives — a refused registration changes nothing.
    assert provider_seam.discover_providers()["github"] is first
    assert provider_seam.registered_names() == ["github"]


def test_e001_unit_002_a_broken_factory_is_skipped_not_fatal() -> None:
    """One provider that cannot be built must not take the others down with it."""

    def broken():
        raise RuntimeError("this extension is misconfigured")

    provider_seam.register_provider("broken", broken)
    provider_seam.register_provider("alpha", factory(StubProvider(name="alpha")))

    discovered = provider_seam.discover_providers()

    assert list(discovered) == ["alpha"]
    assert "broken" in provider_seam.registered_names(), (
        "the registration stands; it is the instantiation that failed, and that is an alarm"
    )
