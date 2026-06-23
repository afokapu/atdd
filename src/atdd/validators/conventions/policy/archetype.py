"""Reusable graph-question archetype for the `policy` family (#1204)."""
from __future__ import annotations

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='policy',
        template_id='forbidden_construct_absence',
        question='Are forbidden constructs, fields, edge types, commands, or legacy shapes absent?',
        selector='graph nodes/artifacts matched by a policy scope',
        traversal='scope -> scan nodes/fields/edges/artifacts -> forbidden matcher',
        invariant='forbidden match set is empty',
        auto_capture='usually explicit; a new node is included if it falls inside a policy scope',
        failure_evidence=['matched_construct', 'policy_id', 'location', 'reason', 'suggested_replacement'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]
