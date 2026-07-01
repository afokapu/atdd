"""Reusable graph-question archetype for the `uniqueness` family (#1204)."""
from __future__ import annotations

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='uniqueness',
        template_id='scoped_identifier_uniqueness',
        question='Within a declared scope, does each identifier appear only once?',
        selector='nodes grouped by identity_scope',
        traversal='scope -> collect node ids -> count occurrences',
        invariant='count(id) == 1 within scope',
        auto_capture='a new node is included if it declares an id and identity scope',
        failure_evidence=['duplicate_id', 'scope', 'locations', 'node_kinds'],
    ),
    TemplateContract(
        family_id='uniqueness',
        template_id='duplicate_edge_absence',
        question='Does a source node avoid declaring the same edge to the same target more than once?',
        selector='nodes with outgoing edges',
        traversal='source node -> outgoing edges grouped by edge_type + target_id',
        invariant='each source/edge_type/target tuple appears once',
        auto_capture='a new node is included if it declares graph edges using standard edge metadata',
        failure_evidence=['source_node', 'edge_type', 'target_node', 'duplicate_locations'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]
