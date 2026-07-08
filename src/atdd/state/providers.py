"""Provider-agnostic SyncProvider registry & discovery (#1364, ext#40 Phase 2).

Core stays **provider-agnostic**: it never imports GitHub (or any provider).
Instead, `atdd state sync` asks this module for the providers to drive, and a
provider is supplied by whoever installed it:

- **Primary — in-process registration.** An extension-owned runner (or a test)
  calls :func:`register_provider` with a factory. This is the primary mechanism
  because atdd extensions are *directory-based declarative packages* discovered by
  ``rglob("atdd.implementation.yaml")`` — they are **not** pip distributions and
  register **no** Python entry points, so entry-point discovery finds nothing from
  them. The provider itself never imports ``atdd`` (it duck-types the store); the
  runner is the composition root that wires the two together.
- **Secondary — entry-point discovery.** A genuinely pip-installed provider package
  may declare an ``atdd.state.sync_providers`` entry point whose value is a factory
  (``() -> SyncProvider``). This mirrors the ``pytest11`` precedent and lets a
  packaged provider self-register with zero core edits.

With **zero** providers, :func:`discover_providers` returns an empty mapping — the
sync engine then runs pure-local (the outbox stays pending, the inbox drains).

Dependency discipline: stdlib only + ``atdd.state`` (never any provider import).
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, List

from atdd.state.sync_engine import SyncProvider

_log = logging.getLogger(__name__)

#: Entry-point group a pip-installed provider package declares to self-register.
ENTRY_POINT_GROUP = "atdd.state.sync_providers"

#: A zero-arg factory returning a ready-to-use provider.
ProviderFactory = Callable[[], SyncProvider]

_REGISTRY: Dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Register a :class:`SyncProvider` *factory* under ``name`` (in-process seam).

    Idempotent-by-overwrite: registering the same name again replaces the factory.
    """
    _REGISTRY[name] = factory


def unregister_provider(name: str) -> None:
    """Remove an in-process registration (no-op if absent)."""
    _REGISTRY.pop(name, None)


def clear_providers() -> None:
    """Drop all in-process registrations (test hygiene)."""
    _REGISTRY.clear()


def registered_names() -> List[str]:
    """Sorted names of the in-process registrations."""
    return sorted(_REGISTRY)


def _entry_point_factories() -> Dict[str, ProviderFactory]:
    """Discover provider factories declared via the entry-point group (secondary).

    One bad entry point must never break discovery — a load failure is logged and
    skipped so the remaining providers (and pure-local sync) still work.
    """
    out: Dict[str, ProviderFactory] = {}
    try:
        from importlib.metadata import entry_points
    except Exception:  # pragma: no cover - importlib.metadata always present on 3.10+
        return out
    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:  # pragma: no cover - Python <3.10 grouped-dict API
        eps = entry_points().get(ENTRY_POINT_GROUP, [])  # type: ignore[attr-defined]
    for ep in eps:
        try:
            out[ep.name] = ep.load()
        except Exception as exc:  # noqa: BLE001 - one bad entry must not abort discovery
            _log.warning("sync provider entry-point failed to load",
                         extra={"entry_point": ep.name, "group": ENTRY_POINT_GROUP,
                                "error": str(exc)})
    return out


def discover_providers() -> Dict[str, SyncProvider]:
    """Build the ``{name: SyncProvider}`` mapping from every registration mechanism.

    In-process :func:`register_provider` entries take precedence over entry points
    of the same name. A factory that raises is logged and skipped. Zero providers →
    empty mapping → pure-local sync.
    """
    factories: Dict[str, ProviderFactory] = {}
    factories.update(_entry_point_factories())
    factories.update(_REGISTRY)  # in-process registrations win
    providers: Dict[str, SyncProvider] = {}
    for name, factory in factories.items():
        try:
            providers[name] = factory()
        except Exception as exc:  # noqa: BLE001 - a broken factory must not abort the rest
            _log.warning("sync provider factory failed",
                         extra={"provider": name, "error": str(exc)})
    return providers
