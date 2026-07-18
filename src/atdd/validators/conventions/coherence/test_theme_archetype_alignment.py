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

from atdd.validators.conventions.coherence import _parity
from atdd.validators.conventions.coherence.archetype import (
    TEMPLATE_IDS,
    resolved_fact_agreement,
)
from atdd.validators.conventions.coherence.fixtures import build_archetype_graph

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


def test_fault_injection_convention_catches() -> None:
    """Inject a misaligned `code` wagon into the real tree; the convention evaluator
    catches it; revert. Oracle retired (#1365)."""
    root = _parity.repo_root()
    pkg = "zz_archetype_probe"
    manifest = root / "plan" / pkg / f"_{pkg}.yaml"
    wrong_src = root / "src" / "atdd" / "planner" / pkg / "__init__.py"  # atdd:suppress(coach.code-roots.no-hardcoded-toolkit-root) — #1499 ratchet: pre-existing toolkit-layout hardcode; destination is zero
    entries = [
        (manifest, 'wagon: zz-archetype-probe\nurn: "wagon:zz-archetype-probe"\ntheme: code\n'),
        (wrong_src, ""),
    ]
    with _parity.temp_paths(entries):
        conv = _parity.conv_violations(VARIANT, root)
    assert conv, "convention evaluator did not catch the archetype misalignment"
    assert _parity.conv_violations(VARIANT, root) == [], "fault did not revert cleanly"


def test_fragment_valid_clean_and_invalid_caught(tmp_path: Path) -> None:
    """Filesystem-bound variant: build aligned vs misaligned tmp fragments."""
    aligned = build_archetype_graph(tmp_path / "ok", aligned=True)
    misaligned = build_archetype_graph(tmp_path / "bad", aligned=False)
    assert resolved_fact_agreement(aligned, {"variant": VARIANT}) == []
    assert resolved_fact_agreement(misaligned, {"variant": VARIANT})
