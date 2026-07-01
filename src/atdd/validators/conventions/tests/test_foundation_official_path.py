# URN: test:validate-conventions:convention-graph-query-contract:foundation-official-path
# WMBT: wmbt:validate-conventions:E019
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Foundation (#1212 decommission build): the OFFICIAL variant execution path
`archetype.evaluate(real_graph, config)` runs against the real composed graph.

Before this, `evaluators.py` was fixture-dict-shaped and crashed on the real graph
(`TypeError: 'method' object is not iterable`); real execution lived only in the
parallel `_support.sentinels`. This proves the real graph is now the canonical
execution substrate the variants run through.
"""
from __future__ import annotations

import importlib
from pathlib import Path

from atdd.validators.conventions._support.graph_loader import load_composed_graph

# template_id -> family, for every template ported onto the real graph in the foundation.
PORTED = {
    "identifier_grammar_conformance": "grammar",
    "scoped_identifier_uniqueness": "uniqueness",
    "node_schema_conformance": "schema",
    "direct_reference_resolution": "resolution",
    "artifact_reference_resolution": "resolution",
    "reference_chain_resolution": "resolution",
    "declaration_to_implementation_binding": "binding",
    "composed_graph_loads": "composition",
    "emitted_identity_roundtrip": "binding",
}


def _template(family: str, template_id: str):
    mod = importlib.import_module(f"atdd.validators.conventions.{family}.archetype")
    by_id = {t.template_id: t for t in mod.TEMPLATES}
    assert template_id in by_id, f"{template_id} not declared in {family} archetype"
    return by_id[template_id]


def test_official_path_executes_on_real_graph(repo_root: Path) -> None:
    g = load_composed_graph(repo_root)
    for template_id, family in PORTED.items():
        tc = _template(family, template_id)
        ev = tc.evaluate(g)  # official path on the REAL graph — must not crash
        assert isinstance(ev, list), f"{family}/{template_id} did not return evidence list"
        # the real repo is valid, so every ported template is clean on it
        assert ev == [], f"{family}/{template_id} unexpectedly flagged the clean repo: {ev[:2]}"


def test_config_param_is_accepted(repo_root: Path) -> None:
    g = load_composed_graph(repo_root)
    tc = _template("grammar", "identifier_grammar_conformance")
    # evaluate(graph, config) signature is honored end-to-end
    assert tc.evaluate(g, config={"variant": "wmbt_urn"}) == []
