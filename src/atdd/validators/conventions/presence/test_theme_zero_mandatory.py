# URN: test:validate-conventions:presence-variants:theme_zero_mandatory
# Acceptance: acc:govern-lifecycle:C006-UNIT-001-override-cannot-remove-commons-floor
# Acceptance: acc:govern-lifecycle:C006-UNIT-002-defaults-contain-commons-floor
# Acceptance: acc:govern-lifecycle:C006-SMOKE-001-repo-config-keeps-commons-floor
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `presence/theme_zero_mandatory` (#1206).

Instantiates the `presence/required_field_presence` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.validators.conventions.presence import archetype
from atdd.validators.conventions.presence.archetype import TEMPLATE_IDS
from atdd.validators.conventions._support.graph_loader import load_composed_graph

from .conftest import patched

FAMILY = "presence"
TEMPLATE = "required_field_presence"
VARIANT = "theme_zero_mandatory"
QUESTION = 'Does every eligible node declare the fields required by its convention/schema?'
SELECTOR = 'nodes whose schema/kind declares required fields'
TRAVERSAL = 'node -> required_fields'
INVARIANT = 'every required field exists and is non-empty'
AUTO_CAPTURE = 'a new node is included if its schema/kind declares required fields'
FAILURE_EVIDENCE = ['node_id', 'missing_field', 'schema_id', 'node_location']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_theme_zero_mandatory.py']


_TC = {t.template_id: t for t in archetype.TEMPLATES}
THEME_CONVENTION = "src/atdd/planner/conventions/theme.convention.yaml"


def _evaluate(graph) -> list:
    return _TC[TEMPLATE].evaluate(graph, {"variant": VARIANT})


def test_theme_zero_mandatory_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in presence archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_theme_zero_clean_baseline(clean_convention_graph) -> None:
    """Real composed graph: the commons floor is declared, so 0 violations."""
    assert _evaluate(clean_convention_graph) == []


@pytest.mark.convention_filesystem_mutation
def test_theme_zero_catches_injected_fault(repo_root: Path) -> None:
    """Renaming the digit-0 token away from `commons` in the real convention is caught,
    with template-shaped evidence."""
    with patched(repo_root, THEME_CONVENTION,
                 'theme_zero_token: "commons"', 'theme_zero_token: "platform"'):
        violations = _evaluate(load_composed_graph(repo_root))
    assert any(v["node_id"] == "theme.taxonomy.commons-floor" for v in violations)
    for v in violations:
        assert set(v).issubset(set(FAILURE_EVIDENCE)), f"evidence not template-shaped: {set(v)}"


@pytest.mark.convention_filesystem_mutation
def test_theme_zero_is_convention_only_legacy_is_tautological(repo_root: Path) -> None:
    """PARITY CLASSIFICATION: CONVENTION-ONLY (legacy is tautological, un-faultable).

    The legacy validator's ``resolve_theme_set`` sets ``resolved['0'] =
    CANONICAL_THEME_0`` and then asserts equality against that SAME constant, so it
    is structurally tautological and cannot be made to fail by any repo-data fault
    (proven by its own ``test_override_cannot_remove_commons_floor``). The same
    YAML fault that this convention variant catches leaves the legacy validator
    green — so this variant ADDS the real, data-level commons-floor gate that
    legacy never provided. Parity-both is therefore not achievable; we assert the
    divergence explicitly rather than fake it.
    """
    with patched(repo_root, THEME_CONVENTION,
                 'theme_zero_token: "commons"', 'theme_zero_token: "platform"'):
        convention_caught = bool(_evaluate(load_composed_graph(repo_root)))
    # oracle retired (#1365): the convention evaluator is the live coverage (it was
    # already stricter than the legacy tautology — convention-only by construction).
    assert convention_caught, (
        "convention evaluator did not catch the theme_zero-token fault"
    )
