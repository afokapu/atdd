# URN: component:validate-conventions:tune-convention-suite:graph-mutations:backend:domain
# Runtime: python
# Purpose: Generic in-memory convention-graph fault injection for the suite (#1415, E033).
"""Inject convention-graph faults into a deep-cloned graph, never onto disk (#1415).

Fault-injection tests historically rewrote a real ``*.convention.yaml`` on disk, evaluated
the family template, then reverted in a ``finally``. That cost THREE graph builds per
variant (pre-state, faulted, post-revert) and mutated the working tree, which blocks
parallelism and risks a residue if the revert is skipped.

These helpers inject the SAME semantic fault into a deep copy of the already-composed
graph instead. The shared session ``clean_convention_graph`` (#1414, E032) is never
touched and no rebuild is triggered.

The helpers are deliberately GENERIC — they name no family. Phase C (#1416) reuses them
for other families, so nothing here hardcodes ``binding`` specifics.
"""
from __future__ import annotations

import copy

from atdd.validators.conventions._support.graph_loader import ConventionGraph


def clone_graph(graph: ConventionGraph) -> ConventionGraph:
    """Return a deep copy so a caller can mutate node ids without touching the shared graph.

    ``deepcopy`` reproduces the graph's internal aliasing: the ``Node`` reached via
    ``_by_id[id]`` is the SAME object as its entry in ``_nodes``, so a later id rename
    stays consistent across both views. No file is read — this is pure in-memory work,
    far cheaper than another ``load_composed_graph`` build.
    """
    return copy.deepcopy(graph)


def rename_rule_id(
    graph: ConventionGraph, old_id: str, suffix: str = "-PARITYBROKEN"
) -> str:
    """Rename a rule node's DECLARATION id in place, leaving the emission index untouched.

    This is the injected declaration<->implementation roundtrip break, semantically
    identical to the on-disk ``rule_id:`` rewrite it replaces: the rule's declaration id
    moves to ``old_id + suffix`` while its ``bind_rule(old_id)`` emission — recorded in
    ``_emits`` by the source scan, NOT by the rule declaration — does not. The emitted
    identity therefore no longer resolves back to the declaring rule, and the roundtrip
    template flags exactly that rule.

    Mutates ``graph`` directly, so callers pass a :func:`clone_graph` result — never the
    shared session graph. Returns the new (broken) id.

    Raises ``KeyError`` if ``old_id`` names no node, so a drifted rule id fails loudly
    rather than injecting a no-op fault the caller would read as a vacuous pass.
    """
    node = graph.by_id(old_id)
    if node is None:
        raise KeyError(f"rule id {old_id!r} not present in graph")
    new_id = f"{old_id}{suffix}"
    node.id = new_id
    # Re-key the declaration index; _emits is deliberately left as-is — that gap IS the fault.
    del graph._by_id[old_id]
    graph._by_id[new_id] = node
    return new_id
