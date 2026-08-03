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

from atdd.validators.conventions.presence import archetype
from atdd.validators.conventions.presence.archetype import TEMPLATE_IDS
from atdd.validators.conventions._support.graph_mutations import (
    graph_rooted_at,
    mirror_file,
)

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
# #1639: the theme monolith was deleted; the taxonomy lives on its convention
# node, so that is both what the evaluator reads and what this test faults.
THEME_CONVENTION = (
    "src/atdd/planner/conventions/nodes/"
    "planner.theme.canonical-taxonomy.convention.yaml"
)


def _evaluate(graph) -> list:
    return _TC[TEMPLATE].evaluate(graph, {"variant": VARIANT})


def test_theme_zero_mandatory_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in presence archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_theme_zero_clean_baseline(clean_convention_graph) -> None:
    """Real composed graph: the commons floor is declared, so 0 violations."""
    assert _evaluate(clean_convention_graph) == []


def _staged_broken_floor(repo_root: Path, tmp_path: Path, graph):
    """Mirror the theme taxonomy node with the digit-0 token renamed away from
    ``commons``, and hand back a graph rooted at that staged tree.

    ``presence.archetype._check_theme_zero_mandatory`` reads this node file through
    ``graph.root``, so a redirected root is the whole fault surface: the evaluator
    parses the real file's own bytes plus the rename, and the checkout is never
    written. ``mirror_file`` raises if the anchor has drifted, so the fault cannot go
    vacuous against an un-faulted tree.

    The anchor is the ``theme_zero`` term's ``token: commons`` (#1639) — a unique
    string in the node, and the exact field the evaluator compares against.
    """
    mirror_file(repo_root, tmp_path, THEME_CONVENTION,
                lambda t: t.replace('token: commons',
                                    'token: platform', 1))
    return graph_rooted_at(graph, tmp_path)


def test_theme_zero_catches_injected_fault(
    clean_convention_graph, repo_root: Path, tmp_path: Path
) -> None:
    """Renaming the digit-0 token away from `commons` in the convention is caught,
    with template-shaped evidence.

    NON-VACUITY: this evaluator reports the SAME violation for a missing file as for a
    faulted one (an unreadable convention yields no ``theme_zero_token`` either), so a
    staged tree that silently failed to materialize would still turn this test green. The
    control leg below stages the convention UNFAULTED — a cosmetic trailing comment — and
    requires the evaluator to be clean on it, which it can only be if it really parsed the
    real file's bytes at the real relative path.
    """
    control = mirror_file(repo_root, tmp_path / "control", THEME_CONVENTION,
                          lambda t: t + "\n# staged control (unfaulted)\n")
    assert control.is_file()
    assert _evaluate(graph_rooted_at(clean_convention_graph, tmp_path / "control")) == [], (
        "the unfaulted staged tree reported a commons-floor violation — the staged root is "
        "not being read as the real convention, so the faulted leg would pass vacuously"
    )

    violations = _evaluate(
        _staged_broken_floor(repo_root, tmp_path / "faulted", clean_convention_graph)
    )
    assert any(v["node_id"] == "theme.taxonomy.commons-floor" for v in violations)
    for v in violations:
        assert set(v).issubset(set(FAILURE_EVIDENCE)), f"evidence not template-shaped: {set(v)}"


def test_theme_zero_is_convention_only_legacy_is_tautological(
    clean_convention_graph, repo_root: Path, tmp_path: Path
) -> None:
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
    staged = _staged_broken_floor(repo_root, tmp_path, clean_convention_graph)
    # oracle retired (#1365): the convention evaluator is the live coverage (it was
    # already stricter than the legacy tautology — convention-only by construction).
    assert _evaluate(staged), (
        "convention evaluator did not catch the theme_zero-token fault"
    )
    # The untouched session graph stays silent: the fault is in the staged tree only.
    assert _evaluate(clean_convention_graph) == []
