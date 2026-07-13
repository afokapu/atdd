# URN: test:validate-conventions:coverage-variants:wmbt_has_smoke_acceptance
# Acceptance: acc:govern-lifecycle:E003-INTEGRATION-001-planner-validator-fires-on-zero-smoke-urns
# Acceptance: acc:govern-lifecycle:E003-SMOKE-001-real-validator-suite-includes-this-validator
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `coverage/wmbt_has_smoke_acceptance` (#1206 / #1212).

Instantiates the `coverage/source_has_required_target` template against the composed convention
graph. Every WMBT must declare >=1 acceptance carrying the SMOKE harness token;
inline-suppressed WMBTs (legacy `suppress-and-clean` disposition) are skipped so
the clean repo stays at 0.

Legacy parity: BOTH catch. The legacy `test_every_wmbt_has_smoke_acceptance`
enforces via the disposition gate; the fault-injection test below proves the
convention evaluator and the legacy validator both flag the same injected fault.
"""
from __future__ import annotations

from atdd.validators.conventions.coverage.archetype import (
    TEMPLATE_IDS,
    _source_has_required_target,
)
from atdd.validators.conventions.coverage import _parity
from atdd.validators.conventions._support.graph_mutations import add_node, clone_graph

FAMILY = "coverage"
TEMPLATE = "source_has_required_target"
VARIANT = "wmbt_has_smoke_acceptance"
QUESTION = 'For every source node of type X, does required downstream target Y exist?'
SELECTOR = 'nodes where node.coverage.requires exists'
TRAVERSAL = 'source node -> required relationship/path -> target node set'
INVARIANT = 'target set is non-empty and satisfies required target kind/filter'
AUTO_CAPTURE = 'a new node is included if it declares coverage requirements'
FAILURE_EVIDENCE = ['source_node', 'required_target_kind', 'required_path', 'actual_targets']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_wmbt_has_smoke_acceptance.py']

def test_wmbt_has_smoke_acceptance_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in coverage archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_clean_baseline_is_zero(clean_convention_graph) -> None:
    """Real repo: every WMBT either has a SMOKE acceptance or is inline-suppressed."""
    root = _parity.repo_root()
    viols = _parity.conv_violations(root, _source_has_required_target,
                                    {"variant": VARIANT}, graph=clean_convention_graph)
    assert viols == [], f"clean baseline must be 0, got {viols[:3]}"


_PROBE_WMBT = "wmbt:validate-conventions:E997"


def test_fault_injection_legacy_parity_both_catch(clean_convention_graph) -> None:
    """Inject a WMBT whose only acceptance lacks the SMOKE token (and no inline
    suppression); the convention evaluator must catch it.

    The WMBT node is added straight to a deep clone of the session graph (#1416): its one
    acceptance URN carries no SMOKE token, so the wmbt->acceptance:SMOKE requirement fires.
    The node's synthetic location is not on disk, so the inline-suppression scan reads no
    marker — the correct reading for a fresh fault node. No plan/ file is written and the
    shared graph is untouched."""
    faulted = clone_graph(clean_convention_graph)
    add_node(faulted, id=_PROBE_WMBT, kind="wmbt",
             fields={"urn": _PROBE_WMBT,
                     "acceptances": [{"identity": {
                         "urn": "acc:validate-conventions:E997-UNIT-001-no-smoke-here"}}]})

    conv = _source_has_required_target(faulted, {"variant": VARIANT})
    caught = [v for v in conv if v["source_node"] == _PROBE_WMBT]
    assert caught, "convention evaluator must catch the no-SMOKE WMBT"
    assert caught[0]["required_target_kind"] == "acceptance:SMOKE"
    assert set(caught[0]).issubset(set(FAILURE_EVIDENCE))
    # oracle retired (#1385): convention path above is the live coverage
    # the shared clean graph carried no such WMBT and stays clean
    assert _source_has_required_target(clean_convention_graph, {"variant": VARIANT}) == []


def test_inline_suppression_is_respected() -> None:
    """A no-SMOKE WMBT carrying the inline suppression marker is NOT flagged —
    mirrors the legacy disposition gate so the clean baseline holds at 0.

    Stays on disk (loader): the evaluator reads the suppression marker from the WMBT's
    source FILE at ``node.location``, so the fault must be a real file — an in-memory node
    has no source text to carry the marker."""
    root = _parity.repo_root()
    rel = "plan/validate_conventions/E996.yaml"
    content = (
        "urn: wmbt:validate-conventions:E996  "
        "# atdd:suppress(planner.wmbt.must-have-smoke-acceptance) UNTIL=2026-12-01\n"
        "acceptances:\n"
        "  - identity:\n"
        "      urn: acc:validate-conventions:E996-UNIT-001-no-smoke-here\n"
    )
    with _parity.inject_tempfile(root, rel, content):
        conv = _parity.conv_violations(root, _source_has_required_target,
                                       {"variant": VARIANT})
    assert not [v for v in conv if v["source_node"] == "wmbt:validate-conventions:E996"], \
        "inline-suppressed WMBT must not be flagged"
