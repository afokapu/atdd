# URN: test:validate-conventions:resolution-variants:contract_consumer_resolution
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `resolution/contract_consumer_resolution` (#1206).

Instantiates the `resolution/artifact_reference_resolution` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

from pathlib import Path

from atdd.validators.conventions.resolution.archetype import TEMPLATE_IDS
from atdd.validators.conventions.resolution._parity import (
    evaluate_variant,
    repo_root,
)

FAMILY = "resolution"
TEMPLATE = "artifact_reference_resolution"
VARIANT = "contract_consumer_resolution"
QUESTION = 'Does every file, schema, fixture, or URN artifact reference resolve to a real artifact?'
SELECTOR = 'nodes with artifact_refs/file_refs/schema_refs/fixture_refs'
TRAVERSAL = 'node -> artifact reference -> repository artifact index'
INVARIANT = 'artifact exists and is addressable from repo root/package root'
AUTO_CAPTURE = 'a new node is included if it declares artifact references with standard metadata'
FAILURE_EVIDENCE = ['node_id', 'artifact_ref', 'artifact_kind', 'expected_path', 'node_location']
LEGACY_PARITY_SOURCES = ['src/atdd/coach/validators/test_validate_contract_consumers.py']


def test_contract_consumer_resolution_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in resolution archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_clean_baseline_is_zero(clean_convention_graph) -> None:
    """The template executes against the real composed graph with no violations."""
    assert evaluate_variant(TEMPLATE, VARIANT, graph=clean_convention_graph) == []


def test_legacy_parity_not_measurable_via_injection() -> None:
    """Honest parity verdict: legacy-hermetic — parity not measurable by injection.

    The legacy counterpart (`test_validate_contract_consumers.py`) is a HERMETIC
    unit test: it constructs a synthetic plan/contracts tree under `tmp_path` and
    exercises `ConsumerValidator` in isolation. It never scans the real repo, so
    no fault injected into the real tree can flip its outcome — a differential
    catch-matrix cell is structurally impossible, and claiming `both` would be
    fabricated parity.

    We assert the hermetic shape (so this classification stays honest if the
    legacy test ever changes) and that the convention path still executes against
    the real graph. The bidirectional consumer-metadata question the legacy unit
    test covers also has no real consume->contract reference data in this repo,
    so there is nothing to resolve on the real graph either — documented, not
    faked.
    """
    legacy_src = Path(LEGACY_PARITY_SOURCES[0])
    if not legacy_src.is_absolute():
        legacy_src = repo_root() / legacy_src
    text = legacy_src.read_text(encoding="utf-8")
    assert "tmp_path" in text, "legacy test expected to be hermetic (tmp_path)"
    assert "ConsumerValidator" in text
    # It does not resolve against the real repo root (no real-repo scan helper).
    assert "find_repo_root" not in text
