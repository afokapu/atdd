# URN: test:validate-conventions:policy-variants:freedom_layer_bash_scope
# Acceptance: acc:govern-lifecycle:E067-SMOKE-001-live-freedom-layer-passes-flipped-validator
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `policy/freedom_layer_bash_scope` (#1212, E032).

Real-graph execution of the `policy/forbidden_construct_absence` template: reads the
real `session.convention.yaml::spawn_time.freedom_layer` and forbids any
`allowed_bash` entry that is not tightly scoped `Bash(<cmd>:*)` or that
pre-authorizes a `forbidden_bash` command. Parity-bound to the legacy coach E032
freedom-layer validator (live SMOKE).
"""
from __future__ import annotations

import yaml

from atdd.validators.conventions._support.graph_mutations import (
    graph_rooted_at,
    mirror_file,
)
from atdd.validators.conventions.policy.archetype import (
    TEMPLATES,
    TEMPLATE_IDS,
    _SESSION_CONVENTION,
)
from atdd.validators.conventions.policy import _parity

FAMILY = "policy"
TEMPLATE = "forbidden_construct_absence"
VARIANT = "freedom_layer_bash_scope"
QUESTION = 'Are forbidden constructs, fields, edge types, commands, or legacy shapes absent?'
SELECTOR = 'graph nodes/artifacts matched by a policy scope'
TRAVERSAL = 'scope -> scan nodes/fields/edges/artifacts -> forbidden matcher'
INVARIANT = 'forbidden match set is empty'
AUTO_CAPTURE = 'usually explicit; a new node is included if it falls inside a policy scope'
FAILURE_EVIDENCE = ['matched_construct', 'policy_id', 'location', 'reason', 'suggested_replacement']
LEGACY_PARITY_SOURCES = [
    'src/atdd/coach/validators/test_e032_smoke_001_live_freedom_layer_passes_flipped_validator.py'
]


def _template():
    return next(t for t in TEMPLATES if t.template_id == TEMPLATE)


def test_freedom_layer_bash_scope_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in policy archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE) <= set(_template().failure_evidence)


def test_clean_baseline_zero_on_real_graph(clean_convention_graph) -> None:
    violations = _template().evaluate(clean_convention_graph, {"variant": VARIANT})
    assert violations == [], (
        f"{VARIANT}: clean repo must yield zero violations, got: {violations}"
    )


def _preauthorize_forbidden(text: str) -> str:
    """Append a forbidden command to the freedom_layer allow-list — the E032 fault."""
    data = yaml.safe_load(text)
    data["spawn_time"]["freedom_layer"]["allowed_bash"].append("Bash(git push:*)")
    return yaml.safe_dump(data, sort_keys=False)


def test_fault_injection_legacy_parity(clean_convention_graph, tmp_path) -> None:
    """Pre-authorize a forbidden command in a staged copy of the freedom_layer
    allow-list; assert the convention evaluator catches it and the real convention
    source is untouched.

    `_read_freedom_layer` yaml-loads the whole session convention FILE under
    `graph.root` — it is deliberately not a graph node ("it is data, not a wagon/rule
    node"), so there is nothing to mutate in memory and the fault must be a real YAML
    the evaluator really parses. Staging it under `tmp_path` from the real file's own
    bytes gives exactly that without rewriting `session.convention.yaml` in the working
    tree — which the loader would otherwise re-read for the rest of the session
    (#1458, E035).

    Oracle retired (#1365): the convention path below is the live coverage.
    """
    root = _parity.repo_root()
    mirror_file(root, tmp_path, _SESSION_CONVENTION, _preauthorize_forbidden)

    staged = graph_rooted_at(clean_convention_graph, tmp_path)
    conv = _template().evaluate(staged, {"variant": VARIANT})
    assert any("git push" in v.get("matched_construct", "") for v in conv), (
        f"{VARIANT}: convention evaluator did not catch the forbidden allowed_bash entry"
    )

    # The real freedom_layer pre-authorizes nothing forbidden and was never written to.
    assert _template().evaluate(clean_convention_graph, {"variant": VARIANT}) == []
