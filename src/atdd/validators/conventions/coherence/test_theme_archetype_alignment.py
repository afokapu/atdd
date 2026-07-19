# URN: test:validate-conventions:coherence-variants:theme_archetype_alignment
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `coherence/theme_archetype_alignment` (#1206).

Instantiates the `coherence/resolved_fact_agreement` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.validators.conventions.coherence import _parity
from atdd.validators.conventions.coherence.archetype import (
    TEMPLATE_IDS,
    resolved_fact_agreement,
)
from atdd.validators.conventions.coherence.fixtures import build_archetype_graph
from atdd.validators.conventions._support.graph_mutations import (
    add_node,
    graph_rooted_at,
    stage_file,
)

FAMILY = "coherence"
TEMPLATE = "resolved_fact_agreement"
VARIANT = "theme_archetype_alignment"
QUESTION = 'After references resolve, do the resolved facts agree with each other?'
SELECTOR = 'nodes declaring coherence checks or semantic comparison rules'
TRAVERSAL = 'source node -> resolved fact A; source node -> resolved fact B; compare A and B'
INVARIANT = 'facts satisfy comparison predicate'
AUTO_CAPTURE = 'partial; a new node is included only if it declares a known coherence predicate'
FAILURE_EVIDENCE = ['source_node', 'fact_a', 'fact_b', 'predicate', 'actual_values']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_theme_archetype_alignment.py']


def test_theme_archetype_alignment_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in coherence archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


# --- executable graph-question tests ---------------------------------------
# PARITY: full subprocess differential. Clean baseline is 0 (every repo wagon is
# `commons`, which carries no archetype-root constraint -> vacuously aligned). The
# fault (a `code`-themed wagon whose source lives under the planner root) is caught
# by BOTH the convention evaluator and the legacy pytest target on identical input.


def test_clean_baseline_is_zero(clean_convention_graph) -> None:
    assert _parity.conv_violations(VARIANT, graph=clean_convention_graph) == []


def test_fault_injection_convention_catches(clean_convention_graph, tmp_path: Path) -> None:
    """A misaligned `code` wagon — implementation under the PLANNER root — is caught.

    The fault has two halves and neither needs the checkout (#1415, #1458). The wagon
    itself is a NODE: the evaluator reads ``w.theme`` and the wagon slug off the graph, so
    dropping a manifest into plan/ only ever existed to make the loader build that node —
    ``add_node`` builds it directly from the same fields. The misplaced SOURCE, though, is
    read from the filesystem (``src_root.rglob(slug)``), so it has to be a real directory
    — staged under a temp root, with the graph re-rooted there.

    Real wagons are unaffected by the redirect: their source dirs do not exist under the
    temp root, so the evaluator reads them as documentation-only and skips them. The probe
    is the only node that can be flagged, which is what makes the assertion precise.
    """
    slug, pkg = "zz-archetype-probe", "zz_archetype_probe"
    probe = "wagon:zz-archetype-probe"

    # The misplaced implementation: a `code`-themed wagon whose source sits under planner/.
    stage_file(tmp_path, f"src/atdd/planner/{pkg}/__init__.py", "")
    staged = graph_rooted_at(clean_convention_graph, tmp_path)
    add_node(staged, id=probe, kind="wagon", theme="code",
             location=f"plan/{pkg}/_{pkg}.yaml",
             fields={"wagon": slug, "urn": probe, "theme": "code"})

    conv = _parity.conv_violations(VARIANT, graph=staged)
    caught = [v for v in conv if v["source_node"] == probe]
    assert caught, f"convention evaluator did not catch the archetype misalignment: {conv}"
    assert caught[0]["actual_values"]["expected_root"] == "coder", (
        f"a `code` wagon must be required under the coder root: {caught[0]}"
    )
    # The untouched session graph stays clean — the probe lives only in the staged copy.
    assert _parity.conv_violations(VARIANT, graph=clean_convention_graph) == []


def test_fragment_valid_clean_and_invalid_caught(tmp_path: Path) -> None:
    """Filesystem-bound variant: build aligned vs misaligned tmp fragments."""
    aligned = build_archetype_graph(tmp_path / "ok", aligned=True)
    misaligned = build_archetype_graph(tmp_path / "bad", aligned=False)
    assert resolved_fact_agreement(aligned, {"variant": VARIANT}) == []
    assert resolved_fact_agreement(misaligned, {"variant": VARIANT})
