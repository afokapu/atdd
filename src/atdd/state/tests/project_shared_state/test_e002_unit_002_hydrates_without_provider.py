# URN: test:project-shared-state:hydrate-projection:E002-UNIT-002-hydrates-without-provider
# Acceptance: acc:project-shared-state:E002-UNIT-002-hydrates-without-provider
# WMBT: wmbt:project-shared-state:E002
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: Hydration completes with zero sync providers registered, attempts no provider lookup, and carries external_refs verbatim without ever consulting them to derive phase (I7). Refs #1433.
"""Hydration is provider-free, and external_refs are inert (E002-UNIT-002).

wagon: project-shared-state | feature: hydrate-projection | phase: GREEN
WMBT: wmbt:project-shared-state:E002

I7: the GitHub mirror is non-authoritative and lifecycle code may not read
``external_refs`` (spec §8.2 rule 5). The decidable form of "no provider lookup is
attempted" is structural — the hydration path holds no reference to the provider
registry at all — plus behavioural: a document whose external_refs *disagree* with
its phase hydrates to the phase the YAML declares, not to anything the mirror says.
Refs #1433 / #1400.
"""
from __future__ import annotations

import ast
from pathlib import Path

import yaml

import atdd.state.projection as projection_module
from atdd.state.projection import hydrate
from atdd.state.providers import clear_providers, discover_providers, registered_names

from ._helpers import memory_store

_UID = "wi_01HF7YAT00M78607F000000013"

#: The mirror says this issue is closed and COMPLETE. It is not authoritative:
#: the phase the projection declares is RED, and RED is what must be hydrated.
_DOCUMENT = {
    "uid": _UID,
    "slug": "feature-mirrored",
    "phase": "RED",
    "state": "ACTIVE",
    "owner_actor": "dev-a",
    "body": "mirrored",
    "external_refs": {
        "bot:github": {"issue": "1400", "state": "closed", "phase": "COMPLETE"},
    },
}

#: Names that would betray a provider lookup on the hydration path.
_PROVIDER_NAMES = {"discover_providers", "registered_names", "providers"}


def _referenced_names(module_path: Path) -> set:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    return {
        node.id if isinstance(node, ast.Name) else node.attr
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.Attribute))
    }


def test_e002_unit_002_hydrates_without_provider(tmp_path) -> None:
    """Zero providers registered; hydration succeeds; external_refs never drive phase."""
    clear_providers()
    assert registered_names() == []
    assert discover_providers() == {}

    projection_dir = tmp_path / "projection"
    projection_dir.mkdir()
    (projection_dir / f"{_UID}.yaml").write_text(
        yaml.safe_dump(_DOCUMENT, sort_keys=True), encoding="utf-8",
    )

    with memory_store() as (conn, store):
        result = hydrate(projection_dir, store)
        assert result.hydrated == 1

        obj = store.objects.get(_UID)
        assert obj is not None

        # external_refs are carried verbatim into the store...
        assert obj.data["external_refs"] == _DOCUMENT["external_refs"]

        # ...and never consulted to derive phase: the mirror claims COMPLETE/closed,
        # the projection declares RED, and RED is what the store holds.
        assert obj.state == "RED"

    # No provider lookup is attempted — the hydration module holds no reference to
    # the provider registry, so there is no path on which one could be.
    referenced = _referenced_names(Path(projection_module.__file__))
    assert not (referenced & _PROVIDER_NAMES), sorted(referenced & _PROVIDER_NAMES)
    assert "atdd.state.providers" not in projection_module.__dict__
