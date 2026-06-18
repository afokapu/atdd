# URN: test:admit-substrate:substrate-admission:C002-UNIT-001-ambiguous-alias-refusal
# Acceptance: acc:admit-substrate:C002-UNIT-001-ambiguous-alias-refusal
# WMBT: wmbt:admit-substrate:C002
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C002-UNIT-001 — a unique alias resolves to one canonical id; a shared alias is
refused with both candidates; an unknown alias is refused; a canonical id resolves
directly, bypassing alias ambiguity."""
from __future__ import annotations

import pathlib

import pytest

from atdd.substrate import registry, resolver

INDEX = pathlib.Path(__file__).parent / "fixtures" / "registry" / "index.yaml"


def _entries():
    return registry.load_registry_index(INDEX)


def test_unique_alias_resolves() -> None:
    assert resolver.resolve("demo", _entries()).id == "acme.extension.demo"


def test_ambiguous_alias_refused_with_candidates() -> None:
    with pytest.raises(resolver.AmbiguousAliasError) as exc:
        resolver.resolve("shared", _entries())
    assert set(exc.value.candidates) == {"acme.extension.alpha", "acme.extension.beta"}


def test_unknown_alias_refused() -> None:
    with pytest.raises(resolver.ResolutionError):
        resolver.resolve("does-not-exist", _entries())


def test_canonical_id_resolves_directly() -> None:
    assert resolver.resolve("acme.extension.beta", _entries()).id == "acme.extension.beta"
