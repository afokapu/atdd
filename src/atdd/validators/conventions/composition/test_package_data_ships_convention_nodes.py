# URN: test:validate-conventions:composition-variants:package_data_ships_convention_nodes
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `composition/package_data_ships_convention_nodes` (#1206).

Instantiates the `composition/composed_graph_loads` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from pathlib import Path

from atdd.validators.conventions._support.graph_mutations import (
    graph_rooted_at,
    mirror_file,
)
from atdd.validators.conventions.composition.archetype import TEMPLATE_IDS, TEMPLATES

FAMILY = "composition"
TEMPLATE = "composed_graph_loads"
VARIANT = "package_data_ships_convention_nodes"
QUESTION = 'Can all convention sources be loaded into one composed graph?'
SELECTOR = 'all convention source files/packages'
TRAVERSAL = 'source files -> parse -> local graph fragments -> composed graph'
INVARIANT = 'graph construction succeeds with no parse/load errors'
AUTO_CAPTURE = 'a new node is included if it lives in a convention source path included by the graph loader'
FAILURE_EVIDENCE = ['source_file', 'parse_error', 'node_id_if_available', 'package_id']
LEGACY_PARITY_SOURCES = ['src/atdd/coach/validators/test_composition_data_shipped.py']


_REPO_ROOT = Path(__file__).resolve().parents[5]
_CONFIG = {"variant": VARIANT}
# The package-data declaration the fault removes. Under the #1474 broad-ship policy
# this one line is what ships every convention-node tree, so narrowing it to the
# conventions' own `*.yaml` (which does NOT reach into `nodes/`) reproduces exactly
# the #1369 defect: the archetype conventions ship, their atomised nodes do not.
#
# It used to remove the literal `, "nodes/*.yaml"` fragment, which no longer exists —
# and which is the same brittleness that let the real bug through: a fault keyed to
# one declaration STYLE stops being injectable the moment the style changes, and a
# fault that cannot be injected proves nothing.
_FAULT_GLOB = '"atdd" = ["**/*"]'
_FAULT_REPLACEMENT = '"atdd" = ["*.yaml"]'


def _template():
    by_id = {t.template_id: t for t in TEMPLATES}
    return by_id[TEMPLATE]


def _convention_evidence(graph):
    """Run the variant through the OFFICIAL path: composed graph ->
    TemplateContract.evaluate(graph, config)."""
    return _template().evaluate(graph, config=_CONFIG)


def _drop_package_data_glob(clean_graph, tmp_path):
    """Stage a pyproject.toml with one convention-node package-data glob dropped.

    The evaluator reads pyproject's `tool.setuptools.package-data` off `graph.root`;
    there is no node for it, so the fault has to be a real TOML it really parses. It
    used to be the REAL pyproject.toml, rewritten and reverted in a `finally` — a file
    that is edited by other work in flight, so the window was a genuine collision risk,
    not just a slow one. Mirroring it into `tmp_path` from its own bytes and dropping
    the glob in the copy injects the identical fault against an identical document
    (#1458, E035). `mirror_file` raises if the glob is already absent, so the fault
    can never go vacuous.
    """
    mirror_file(
        _REPO_ROOT, tmp_path, "pyproject.toml",
        lambda t: t.replace(_FAULT_GLOB, _FAULT_REPLACEMENT, 1),
    )
    return graph_rooted_at(clean_graph, tmp_path)


def test_package_data_ships_convention_nodes_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in composition archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_clean_baseline_no_violations(clean_convention_graph) -> None:
    # The real repo ships every required convention-node/schema glob.
    assert _convention_evidence(clean_convention_graph) == []


def test_evidence_keys_subset_of_failure_evidence(clean_convention_graph, tmp_path) -> None:
    # On an injected fault the evidence keys must be a SUBSET of the contract.
    allowed = set(FAILURE_EVIDENCE)
    ev = _convention_evidence(_drop_package_data_glob(clean_convention_graph, tmp_path))
    assert ev, "convention path must flag the dropped glob"
    for record in ev:
        assert set(record).issubset(allowed), f"evidence keys escape contract: {set(record) - allowed}"


def test_fault_injection(clean_convention_graph, tmp_path) -> None:
    # Legacy parity (verdict 'both') was proven against the legacy validator
    # before it was decommissioned (#1207); the convention fault-injection is
    # the live coverage.
    assert _convention_evidence(clean_convention_graph) == [], (
        "convention path must be clean on the real repo"
    )
    staged = _drop_package_data_glob(clean_convention_graph, tmp_path)
    assert bool(_convention_evidence(staged)), "convention path must catch the injected fault"
    # The real pyproject.toml still ships the glob and was never written to.
    assert _convention_evidence(clean_convention_graph) == []
