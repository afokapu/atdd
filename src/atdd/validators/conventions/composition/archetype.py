"""Reusable graph-question archetype for the `composition` family (#1204)."""
from __future__ import annotations

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='composition',
        template_id='composed_graph_loads',
        question='Can all convention sources be loaded into one composed graph?',
        selector='all convention source files/packages',
        traversal='source files -> parse -> local graph fragments -> composed graph',
        invariant='graph construction succeeds with no parse/load errors',
        auto_capture='a new node is included if it lives in a convention source path included by the graph loader',
        failure_evidence=['source_file', 'parse_error', 'node_id_if_available', 'package_id'],
    ),
    TemplateContract(
        family_id='composition',
        template_id='composition_merge_identity',
        question='When graph fragments compose, are node identities merged, duplicated, or shadowed correctly?',
        selector='all nodes grouped by canonical id across packages/fragments',
        traversal='package graph fragments -> canonical node id -> merge policy',
        invariant='duplicate ids are either forbidden or explicitly allowed by merge/override policy',
        auto_capture='a new node is included if it declares canonical identity and package ownership',
        failure_evidence=['node_id', 'conflicting_packages', 'merge_policy', 'locations'],
    ),
    TemplateContract(
        family_id='composition',
        template_id='post_composition_edge_legality',
        question='After composition, are all edges legal under composed graph rules?',
        selector='composed_graph.edges',
        traversal='edge -> source node -> target node -> allowed edge type matrix',
        invariant='edge type is allowed between source kind/package and target kind/package',
        auto_capture='a new node is included if it participates in edges in the composed graph',
        failure_evidence=['edge_type', 'source_node', 'target_node', 'source_kind', 'target_kind', 'reason'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]
