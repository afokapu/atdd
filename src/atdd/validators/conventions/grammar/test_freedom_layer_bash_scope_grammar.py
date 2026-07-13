# URN: test:validate-conventions:grammar-variants:freedom_layer_bash_scope_grammar
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `grammar/freedom_layer_bash_scope_grammar` (#1206).

Instantiates the `grammar/identifier_grammar_conformance` template against the composed convention
graph. Execution lands on the real `_support` graph engine via the family
`REAL_EVALUATORS` (config-parameterized by variant); this module fixes the
variant's contract + legacy parity binding and runs in parallel with the legacy
validators (imports no persona validator module).

Data substrate: `spawn_time.freedom_layer.allowed_bash` in
`src/atdd/coach/conventions/session.convention.yaml` — DATA, not the CLAUDE.md
document (#1062/E031) — so this variant is WIRED, not skipped. Each allowed_bash
entry is a grammar-governed identifier that must conform to `Bash(<cmd>:*)`.

Legacy parity (#1212): the apples-to-apples real-data counterpart is the live
E032 smoke (`test_every_live_allowed_bash_entry_is_scoped`), which reads the same
deployed convention. The E032 *unit* test (test_e032_unit_002) enforces the
identical grammar but over a synthetic in-memory dict, so it cannot participate
in a file-injection differential (it never reads repo state); it is recorded as
the semantic origin only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.validators.conventions._support.graph_loader import load_composed_graph
from atdd.validators.conventions.grammar import archetype
from atdd.validators.conventions.grammar.archetype import TEMPLATE_IDS, TEMPLATES

FAMILY = "grammar"
TEMPLATE = "identifier_grammar_conformance"
VARIANT = "freedom_layer_bash_scope_grammar"
QUESTION = 'Does an identifier, URN, rule id, or node id follow canonical grammar?'
SELECTOR = 'nodes with id/rule_id/urn/name fields'
TRAVERSAL = 'node -> identifier field -> grammar parser'
INVARIANT = 'parser accepts identifier and parsed parts match graph context'
AUTO_CAPTURE = 'a new node is included if it declares a grammar-governed identifier field'
FAILURE_EVIDENCE = ['node_id', 'field', 'value', 'grammar_name', 'parse_error']

# Real-data legacy counterpart (reads the deployed convention) — the file-injection
# parity target. test_e032_unit_002 (synthetic dict) is the semantic origin.
LEGACY_PARITY_SOURCES = [
    "src/atdd/coach/validators/test_e032_smoke_001_live_freedom_layer_passes_flipped_validator.py"
    "::test_every_live_allowed_bash_entry_is_scoped",
]
LEGACY_SEMANTIC_ORIGIN = (
    "src/atdd/coach/validators/test_e032_unit_002_validator_rejects_unscoped_bash_entry.py"
)

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SESSION_CONVENTION_REL = "src/atdd/coach/conventions/session.convention.yaml"


def _template():
    return next(t for t in TEMPLATES if t.template_id == TEMPLATE)


def _evaluate(repo_root, graph=None):
    g = graph if graph is not None else load_composed_graph(repo_root)
    return _template().evaluate(g, config={"variant": VARIANT})




# --- contract --------------------------------------------------------------
def test_freedom_layer_bash_scope_grammar_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in grammar archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_evidence_keys_are_subset_of_template_failure_evidence() -> None:
    """Evidence the variant emits uses only the template's declared
    failure_evidence keys (the template contract)."""
    allowed = set(_template().failure_evidence)
    assert set(FAILURE_EVIDENCE) <= allowed
    # A representative evidence record must carry only declared keys.
    record = {
        "node_id": _SESSION_CONVENTION_REL,
        "field": "spawn_time.freedom_layer.allowed_bash",
        "value": "Bash",
        "grammar_name": "freedom-layer-bash-scope",
        "parse_error": "unscoped/over-broad Bash entry: must be Bash(<cmd>:*)",
    }
    assert set(record) <= allowed


# --- clean baseline --------------------------------------------------------
def test_clean_baseline_zero_on_real_repo(clean_convention_graph) -> None:
    """On the real composed graph the deployed freedom_layer is fully scoped, so
    the variant returns no evidence (non-vacuous: allowed_bash is non-empty)."""
    fl = archetype._freedom_layer(clean_convention_graph)
    assert fl.get("allowed_bash"), "selector vacuous: freedom_layer declares no allowed_bash"
    assert _evaluate(_REPO_ROOT, graph=clean_convention_graph) == []


# --- fault injection + legacy parity ---------------------------------------
@pytest.mark.convention_filesystem_mutation
def test_fault_injection_convention_catches(tmp_path) -> None:
    """Inject an unscoped Bash allow-list entry into the real convention source;
    the convention path (real composed graph) catches it. Revert afterwards.
    Oracle retired (#1365)."""
    conv = _REPO_ROOT / _SESSION_CONVENTION_REL
    original = conv.read_text(encoding="utf-8")
    # A bare, unscoped Bash entry — the canonical E032 fault.
    faulted = original.replace(
        '      - "Bash(pytest:*)"', '      - "Bash(pytest:*)"\n      - "Bash"', 1
    )
    assert faulted != original, "fault-injection anchor not found in convention source"
    try:
        conv.write_text(faulted, encoding="utf-8")

        conv_evidence = _evaluate(_REPO_ROOT)
        assert conv_evidence, "convention path missed the unscoped Bash entry"
        assert any(e["value"] == "Bash" for e in conv_evidence), conv_evidence
        assert all(set(e) <= set(FAILURE_EVIDENCE) for e in conv_evidence)
        # oracle retired (#1365): the convention path above is the live coverage
    finally:
        conv.write_text(original, encoding="utf-8")

    # clean tree is silent afterwards.
    assert _evaluate(_REPO_ROOT) == []
