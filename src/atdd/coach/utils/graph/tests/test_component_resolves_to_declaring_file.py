# URN: test:coach:resolver:component-resolves-to-declaring-file
# Issue: #1753 (child of #1733)
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""#1753 defect 2 — a component URN must resolve to the file that declares it.

``ComponentResolver.resolve`` re-derived a path from layout convention (side and
layer directory guesses, then a filename stem match) and never asked which file
actually carried the ``# URN: component:...`` header. **27 component URNs failed
this tautological resolution** — reported by ``atdd repo broken`` as
"Component file not found" while sitting in the very file that declared them.

The residual set is grammar violations, and they must STAY broken: resolving a
malformed URN to its declaring file would silence a real violation and make
``atdd repo broken`` quieter, which is the opposite of this issue's intent.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.graph.resolver import ComponentResolver
from atdd.coach.utils.repo import find_repo_root


@pytest.fixture(scope="module")
def resolver() -> ComponentResolver:
    return ComponentResolver(find_repo_root())


@pytest.fixture(scope="module")
def declarations(resolver: ComponentResolver):
    return resolver.find_declarations()


def test_every_grammatical_component_resolves_to_its_own_file(
    resolver: ComponentResolver, declarations
) -> None:
    """The tautology: a URN a file declares resolves to that file."""
    failures = []
    for decl in declarations:
        if resolver._validate_urn_format(decl.urn):
            continue  # malformed — asserted separately below
        resolution = resolver.resolve(decl.urn)
        if not resolution.is_resolved:
            failures.append((decl.urn, resolution.error))
        elif decl.source_path not in resolution.resolved_paths:
            failures.append((decl.urn, f"resolved elsewhere: {resolution.resolved_paths}"))

    assert not failures, (
        f"{len(failures)} component URNs do not resolve to their declaring file: "
        f"{failures[:5]}"
    )


def test_malformed_component_urns_stay_broken(
    resolver: ComponentResolver, declarations
) -> None:
    """The declaring-file shortcut must not smuggle malformed URNs past the grammar.

    Without this, the fix would silence real grammar violations and `repo broken`
    would get QUIETER — the failure mode #1753 explicitly forbids.
    """
    malformed = [d for d in declarations if resolver._validate_urn_format(d.urn)]
    assert malformed, "expected the corpus to still carry malformed component URNs"

    for decl in malformed:
        resolution = resolver.resolve(decl.urn)
        assert not resolution.is_resolved, (
            f"malformed URN {decl.urn} resolved anyway — a grammar violation was silenced"
        )
        assert resolution.error


def test_undeclared_component_urn_does_not_resolve(resolver: ComponentResolver) -> None:
    """A well-formed URN no file declares must not resolve to something nearby."""
    resolution = resolver.resolve(
        "component:govern-lifecycle:bind-issue-feature:NoSuchThing:backend:domain"
    )
    assert not resolution.is_resolved
    assert resolution.error


def test_resolution_is_deterministic_for_a_single_declarer(
    resolver: ComponentResolver, declarations
) -> None:
    """One declaring file means one resolved path, not an ambiguous set."""
    seen: dict[str, list[Path]] = {}
    for decl in declarations:
        seen.setdefault(decl.urn, []).append(decl.source_path)

    unique = [u for u, paths in seen.items() if len(set(paths)) == 1]
    assert unique, "expected at least one singly-declared component URN"

    for urn in unique:
        if resolver._validate_urn_format(urn):
            continue
        resolution = resolver.resolve(urn)
        assert resolution.is_deterministic, f"{urn} resolved non-deterministically"
