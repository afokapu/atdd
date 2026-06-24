"""Canonical valid/invalid REAL-graph fragments for the `presence` family (#1212).

Fragments are small ``ConventionGraph`` objects built from real ``Node`` objects
(graph_loader model) — NOT dict fixtures. They exercise the node-traversal
variants in isolation (selector -> traversal -> invariant) without touching disk.

Keyed ``{template_id: {variant: ConventionGraph}}``.

File-backed variants (``theme_zero_mandatory``, ``rule_has_disposition``,
``phase_machine_init_precommit_gate``) read their source through ``graph.root``;
they are exercised against the REAL composed graph + on-disk fault injection in
their variant test modules, not via these in-memory fragments.
"""
from __future__ import annotations

from .._support.graph_loader import ConventionGraph, Node


def _graph(nodes: list) -> ConventionGraph:
    g = ConventionGraph()
    for n in nodes:
        g._add(n)
    return g


def _rule(rule_id: str, fields: dict) -> Node:
    return Node(id=rule_id, kind="rule",
                location="src/atdd/demo/conventions/demo.convention.yaml", fields=fields)


def _feedback_loop_graph(*, with_close_the_loop: bool) -> ConventionGraph:
    acc = {"identity": {"phase": "SMOKE", "urn": "acc:demo:E001-SMOKE-001"}}
    if with_close_the_loop:
        acc["close_the_loop"] = {"consumer_reacted": "asserted", "drift_resolved": "asserted"}
    return _graph([
        Node(id="feature:demo:loop", kind="feature",
             location="plan/demo/features/loop.yaml", package="demo",
             refs=["wmbt:demo:E001"],
             fields={"kind": "feedback-loop", "wmbts": ["wmbt:demo:E001"]}),
        Node(id="wmbt:demo:E001", kind="wmbt", location="plan/demo/E001.yaml",
             package="demo", fields={"acceptances": [acc]}),
    ])


# Real-graph fragments per (template_id, variant).
VALID_FRAGMENTS: dict = {
    "conditional_requirement": {
        "feedback_loop_close_the_loop": _feedback_loop_graph(with_close_the_loop=True),
    },
    "required_field_presence": {
        # rule_has_fix_hint: a fix_hint-declaring rule with a non-empty value.
        "rule_has_fix_hint": _graph([
            _rule("demo.rule.with-hint", {"fix_hint": "run `atdd gate` then retry"}),
            _rule("demo.rule.no-hint-field", {"severity": 3}),  # not selected (no field)
        ]),
    },
}

INVALID_FRAGMENTS: dict = {
    "conditional_requirement": {
        "feedback_loop_close_the_loop": _feedback_loop_graph(with_close_the_loop=False),
    },
    "required_field_presence": {
        # rule_has_fix_hint: a rule declaring an EMPTY fix_hint (presence-of-value fault).
        "rule_has_fix_hint": _graph([
            _rule("demo.rule.empty-hint", {"fix_hint": "   "}),
        ]),
    },
}
