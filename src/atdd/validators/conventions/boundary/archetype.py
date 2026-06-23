"""Reusable graph-question archetype for the `boundary` family (#1204)."""
from __future__ import annotations

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='boundary',
        template_id='allowed_boundary_crossing',
        question='Does this edge, import, or reference cross only allowed package/layer boundaries?',
        selector='edges/imports/references with source and target ownership metadata',
        traversal='source node/package -> edge/import/ref -> target node/package -> boundary policy',
        invariant='boundary_policy.allows(source, target, edge_type)',
        auto_capture='a new node is included if it declares ownership/package/layer metadata and participates in edges',
        failure_evidence=['source', 'target', 'edge_type', 'source_boundary', 'target_boundary', 'violated_policy'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]
