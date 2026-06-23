"""Reusable graph-question archetype for the `coherence` family (#1204)."""
from __future__ import annotations

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='coherence',
        template_id='resolved_fact_agreement',
        question='After references resolve, do the resolved facts agree with each other?',
        selector='nodes declaring coherence checks or semantic comparison rules',
        traversal='source node -> resolved fact A; source node -> resolved fact B; compare A and B',
        invariant='facts satisfy comparison predicate',
        auto_capture='partial; a new node is included only if it declares a known coherence predicate',
        failure_evidence=['source_node', 'fact_a', 'fact_b', 'predicate', 'actual_values'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]
