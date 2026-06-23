"""Reusable graph-question archetype for the `acyclicity` family (#1204)."""
from __future__ import annotations

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='acyclicity',
        template_id='forbidden_cycle_absence',
        question='Does a traversal avoid cycles where cycles are forbidden?',
        selector='edge types or relationship subgraphs marked acyclic',
        traversal='nodes -> selected edge type/path -> depth-first traversal',
        invariant='no node appears twice in the same traversal path',
        auto_capture='a new node is included if it participates in an edge type declared acyclic',
        failure_evidence=['cycle_path', 'edge_type', 'start_node', 'repeated_node'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]
