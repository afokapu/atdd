# URN: test:validate-conventions:presence-variants:acceptance_well_formed
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `presence/acceptance_well_formed` (#1555).

Instantiates the `presence/required_field_presence` template against the composed
convention graph. Every acceptance must carry Given/When/Then prose AND at least
one verifiable outcome — the promise `planner.acceptance.well-formed` states.

Enforcement history (honest): the rule was `planner.acceptance.complete` with
`disposition: documentation-only`, no `implementation:` and no `validation:` block
— the statement was never checked by anything. There is therefore NO legacy
validator to reach parity with; this variant is the first and only enforcement,
and the fault-injection tests below measure that directly.

The name changed with the enforcement: this checks LOCAL SHAPE of one acceptance,
not set-completeness of a WMBT's acceptance collection (that is
`planner.coverage.every-wmbt-must-have`). `complete` overstated it.
"""
from __future__ import annotations

import pytest

from atdd.validators.conventions.presence.archetype import (
    TEMPLATE_IDS,
    evaluate_required_field_presence,
)
from atdd.validators.conventions._support.graph_mutations import add_node, clone_graph

FAMILY = "presence"
TEMPLATE = "required_field_presence"
VARIANT = "acceptance_well_formed"
QUESTION = 'Does every eligible node declare the fields required by its convention/schema?'
SELECTOR = 'nodes whose schema/kind declares required fields'
TRAVERSAL = 'node -> required_fields'
INVARIANT = 'every required field exists and is non-empty'
AUTO_CAPTURE = 'a new node is included if its schema/kind declares required fields'
FAILURE_EVIDENCE = ['node_id', 'missing_field', 'schema_id', 'node_location']
LEGACY_PARITY_SOURCES = []  # none: the rule was documentation-only (see module docstring)

_CONFIG = {"variant": VARIANT}


def test_acceptance_well_formed_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in presence archetype"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_clean_baseline_is_zero(clean_convention_graph) -> None:
    """Real repo: every acceptance carries G/W/T prose and a verifiable outcome."""
    viols = evaluate_required_field_presence(clean_convention_graph, _CONFIG)
    assert viols == [], f"clean baseline must be 0, got {viols[:3]}"


def test_baseline_is_not_vacuous(clean_convention_graph) -> None:
    """The zero above must mean 'all clean', not 'nothing was looked at'.

    A clean_baseline_is_zero assertion on an evaluator that reaches no subjects
    passes forever. This pins that the variant actually traverses the corpus.
    """
    seen = sum(
        len(w.fields.get("acceptances") or []) for w in clean_convention_graph.by_kind("wmbt")
    )
    assert seen > 100, f"variant reached only {seen} acceptances — traversal is broken"


_PROBE_WMBT = "wmbt:validate-conventions:E994"
_PROBE_ACC = "acc:validate-conventions:E994-UNIT-001-probe"


def _faulted(clean_convention_graph, acceptance: dict):
    """A deep clone of the session graph carrying one injected acceptance (#1416).

    Nothing is written to plan/ and the shared graph is untouched.
    """
    faulted = clone_graph(clean_convention_graph)
    add_node(faulted, id=_PROBE_WMBT, kind="wmbt",
             fields={"urn": _PROBE_WMBT, "acceptances": [acceptance]})
    return faulted


def _well_formed_acceptance() -> dict:
    return {
        "identity": {"urn": _PROBE_ACC},
        "given": {"abstract": ["a probe precondition holds"]},
        "when": {"abstract": "the probe evaluator is invoked"},
        "then": {"abstract": ["the probe emits an observable, assertable outcome"]},
    }


def test_positive_control_well_formed_acceptance_is_not_flagged(clean_convention_graph) -> None:
    """The injected-node mechanism itself does not create violations.

    Without this, every fault-injection assertion below could be passing because
    injected nodes are always flagged, rather than because the fault was caught.
    """
    graph = _faulted(clean_convention_graph, _well_formed_acceptance())
    caught = [v for v in evaluate_required_field_presence(graph, _CONFIG)
              if v["node_id"] == _PROBE_ACC]
    assert caught == [], f"a well-formed injected acceptance must be clean, got {caught}"


@pytest.mark.parametrize("section", ["given", "when", "then"])
def test_fault_injection_missing_gwt_prose_is_caught(clean_convention_graph, section) -> None:
    """Drop each Given/When/Then section's prose in turn; each must be caught."""
    acc = _well_formed_acceptance()
    del acc[section]
    graph = _faulted(clean_convention_graph, acc)

    caught = [v for v in evaluate_required_field_presence(graph, _CONFIG)
              if v["node_id"] == _PROBE_ACC]
    assert caught, f"missing {section}.abstract must be caught"
    assert caught[0]["missing_field"] == f"{section}.abstract"
    assert set(caught[0]).issubset(set(FAILURE_EVIDENCE))


@pytest.mark.parametrize("empty", [{"abstract": []}, {"abstract": ""}, {"abstract": ["   "]}, {}])
def test_fault_injection_empty_prose_is_caught(clean_convention_graph, empty) -> None:
    """A present-but-empty section is as unverifiable as an absent one."""
    acc = _well_formed_acceptance()
    acc["given"] = empty
    graph = _faulted(clean_convention_graph, acc)

    caught = [v for v in evaluate_required_field_presence(graph, _CONFIG)
              if v["node_id"] == _PROBE_ACC]
    assert caught, f"empty given.abstract {empty!r} must be caught"
    assert caught[0]["missing_field"] == "given.abstract"


@pytest.mark.parametrize("placeholder", ["TBD", "todo", "N/A", "???", "---", "short"])
def test_fault_injection_unverifiable_outcome_is_caught(clean_convention_graph, placeholder) -> None:
    """`then` prose that states no assertable outcome is caught.

    This is the leg beyond `planner.acceptance.abstract-fields-required`: the
    field is PRESENT and non-empty, so a pure presence check would pass it.
    """
    acc = _well_formed_acceptance()
    acc["then"] = {"abstract": [placeholder]}
    graph = _faulted(clean_convention_graph, acc)

    caught = [v for v in evaluate_required_field_presence(graph, _CONFIG)
              if v["node_id"] == _PROBE_ACC]
    assert caught, f"unverifiable then outcome {placeholder!r} must be caught"
    assert caught[0]["missing_field"] == "then.abstract (no verifiable outcome)"
    assert set(caught[0]).issubset(set(FAILURE_EVIDENCE))


def test_placeholder_mention_inside_real_prose_is_not_flagged(clean_convention_graph) -> None:
    """`TBD` occurring INSIDE a real outcome sentence is not a placeholder.

    The real corpus carries exactly this (`plan/govern_lifecycle/D017.yaml`), so a
    substring match here would put the clean baseline above zero and force the
    check to be weakened. The match is anchored to the whole stripped line.
    """
    acc = _well_formed_acceptance()
    acc["then"] = {"abstract": [
        "A pointer to the follow-on issue is present (or marked TBD if not yet filed)"]}
    graph = _faulted(clean_convention_graph, acc)

    caught = [v for v in evaluate_required_field_presence(graph, _CONFIG)
              if v["node_id"] == _PROBE_ACC]
    assert caught == [], f"prose mentioning TBD is a real outcome, got {caught}"


def test_multiline_when_abstract_array_is_accepted(clean_convention_graph) -> None:
    """`when.abstract` as an array is prose too.

    The corpus carries six such acceptances. This rule checks the narrative is
    PRESENT; which YAML shape carries it is
    `planner.acceptance.abstract-fields-required`'s business, not this rule's.
    """
    acc = _well_formed_acceptance()
    acc["when"] = {"abstract": ["the probe is invoked", "and invoked again"]}
    graph = _faulted(clean_convention_graph, acc)

    caught = [v for v in evaluate_required_field_presence(graph, _CONFIG)
              if v["node_id"] == _PROBE_ACC]
    assert caught == [], f"array when.abstract must be accepted, got {caught}"
