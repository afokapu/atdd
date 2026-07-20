# URN: test:validate-conventions:coverage-variants:train_route_smoke_coverage
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `coverage/train_route_smoke_coverage` (#1206 / #1548).

Instantiates the `coverage/source_has_required_target` template against the composed
convention graph. Every train registered in the plan must have >=1 SMOKE journey test
under its e2e home; a train is the assembly-level journey, and without a smoke test
nothing exercises that route against real infrastructure.

Until #1548 this module was a CONTRACT-ONLY stub: it asserted that the template id was
registered and that the variant declared failure-evidence fields, and executed no
traversal at all. The rule was declared but could not fire.

The e2e home mirrors the train identity (#1421) — typed `train:<subject>:<slug>` lives
at `e2e/<subject>/<slug>/`, legacy `NNNN-slug` at `e2e/NNNN-slug/` — the same mirroring
`plan/_trains/` uses. That derivation is pinned below, because pasting a typed id onto
a path would silently look for a colon-named directory, find nothing, and report every
typed train as uncovered.
"""
from __future__ import annotations

import pytest

from atdd.validators.conventions.coverage.archetype import (
    TEMPLATE_IDS,
    _e2e_home,
    _source_has_required_target,
)
from atdd.validators.conventions.coverage import _parity
from atdd.validators.conventions._support.graph_mutations import (
    add_node,
    clone_graph,
)

FAMILY = "coverage"
TEMPLATE = "source_has_required_target"
VARIANT = "train_route_smoke_coverage"
QUESTION = 'For every source node of type X, does required downstream target Y exist?'
SELECTOR = 'nodes where node.coverage.requires exists'
TRAVERSAL = 'source node -> required relationship/path -> target node set'
INVARIANT = 'target set is non-empty and satisfies required target kind/filter'
AUTO_CAPTURE = 'a new node is included if it declares coverage requirements'
FAILURE_EVIDENCE = ['source_node', 'required_target_kind', 'required_path', 'actual_targets']
LEGACY_PARITY_SOURCES = ['src/atdd/tester/validators/test_train_route_smoke_coverage.py']

_CONFIG = {"variant": VARIANT}
_PROBE_TRAIN = "train:validate-conventions:probe-uncovered-route"


def test_train_route_smoke_coverage_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in coverage archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


# ---------------------------------------------------------------------------
# The e2e home derivation — the piece that is reimplemented, so it is pinned
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "train_id,expected",
    [
        ("train:self-compliance:validate-lifecycle", "e2e/self-compliance/validate-lifecycle"),
        ("train:substrate:author-artifacts", "e2e/substrate/author-artifacts"),
        ("0007-enforce-extension-conventions", "e2e/0007-enforce-extension-conventions"),
    ],
)
def test_e2e_home_mirrors_the_train_identity(tmp_path, train_id, expected):
    home = _e2e_home(tmp_path / "e2e", train_id)
    assert home == tmp_path / expected


def test_typed_train_never_derives_a_colon_named_directory(tmp_path):
    """A colon in the path would make every typed train read as uncovered."""
    home = _e2e_home(tmp_path / "e2e", "train:self-compliance:validate-lifecycle")
    assert ":" not in str(home.relative_to(tmp_path))


# ---------------------------------------------------------------------------
# Clean baseline — asserted together with its own non-vacuity
# ---------------------------------------------------------------------------


def test_clean_baseline_is_zero(clean_convention_graph) -> None:
    """Real repo: every registered train has >=1 smoke test under its e2e home."""
    viols = _parity.conv_violations(
        _parity.repo_root(), _source_has_required_target, _CONFIG,
        graph=clean_convention_graph,
    )
    assert viols == [], f"clean baseline must be 0, got {viols[:3]}"


def test_clean_baseline_actually_evaluated_some_trains(clean_convention_graph) -> None:
    """Guards the assertion above.

    `viols == []` is equally true of a repo with full coverage and of an
    evaluator that selected nothing — a validator that cannot emit passes
    forever. The graph must really carry train nodes for the zero to mean
    anything.
    """
    assert len(clean_convention_graph.by_kind("train")) >= 10


# ---------------------------------------------------------------------------
# Fault injection — the rule must be able to FAIL
# ---------------------------------------------------------------------------


def test_fault_injection_train_without_smoke_is_caught(clean_convention_graph) -> None:
    """Inject a train whose e2e home does not exist; the evaluator must flag it.

    The probe train is added to a deep clone of the session graph (#1416) and its
    e2e home is a path that is not in the tree, so the smoke scan finds nothing.
    No file is written and the shared graph is untouched.
    """
    faulted = clone_graph(clean_convention_graph)
    add_node(faulted, id=_PROBE_TRAIN, kind="train",
             fields={"train_id": _PROBE_TRAIN, "title": "probe"})

    conv = _source_has_required_target(faulted, _CONFIG)
    caught = [v for v in conv if v["source_node"] == _PROBE_TRAIN]

    assert caught, "evaluator must catch a train with no SMOKE journey test"
    assert caught[0]["required_target_kind"] == "test:SMOKE"
    assert caught[0]["actual_targets"] == []
    assert set(caught[0]).issubset(set(FAILURE_EVIDENCE))
    # the shared clean graph carried no such train and stays clean
    assert _source_has_required_target(clean_convention_graph, _CONFIG) == []


def test_fault_evidence_names_the_path_that_was_searched(clean_convention_graph) -> None:
    """The failure must be actionable: it has to say WHERE the smoke test belongs."""
    faulted = clone_graph(clean_convention_graph)
    add_node(faulted, id=_PROBE_TRAIN, kind="train",
             fields={"train_id": _PROBE_TRAIN, "title": "probe"})

    (caught,) = [
        v for v in _source_has_required_target(faulted, _CONFIG)
        if v["source_node"] == _PROBE_TRAIN
    ]
    assert caught["required_path"] == "e2e/validate-conventions/probe-uncovered-route"


def test_a_covered_train_is_not_flagged(clean_convention_graph) -> None:
    """Positive control for the fault above.

    The injected train differs from a real one only in whether its e2e home
    holds a smoke file. Pinning that a REAL train is not flagged proves the
    fault test is detecting absence of coverage and not merely the presence of
    a synthetic node.
    """
    real = [t for t in clean_convention_graph.by_kind("train")
            if (t.fields.get("train_id") or t.id).startswith("train:")]
    assert real, "expected at least one typed train in the repo"

    flagged = {v["source_node"] for v in
               _source_has_required_target(clean_convention_graph, _CONFIG)}
    assert not {t.id for t in real} & flagged
