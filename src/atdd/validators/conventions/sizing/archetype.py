"""Reusable graph-question archetype for the `sizing` family (#1204)."""
from __future__ import annotations

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='sizing',
        template_id='cardinality_bounds',
        question='Is the number of related nodes within allowed min/max bounds?',
        selector='nodes or scopes with declared cardinality constraints',
        traversal='source/scope -> collect related nodes -> count',
        invariant='min <= count <= max',
        auto_capture='a new node is included if it declares cardinality constraints',
        failure_evidence=['source_node_or_scope', 'relationship', 'actual_count', 'min', 'max', 'targets'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]
