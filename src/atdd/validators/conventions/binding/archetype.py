"""Reusable graph-question archetype for the `binding` family (#1204)."""
from __future__ import annotations

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='binding',
        template_id='declaration_to_implementation_binding',
        question='Does a declaration point to a real implementation, validator, or artifact that claims to enforce it?',
        selector='rule/declaration nodes where enforcement requires implementation',
        traversal='declaration node -> implementation_ref -> implementation index',
        invariant='implementation exists and declares compatibility with the declaration',
        auto_capture='a new node is included if it declares enforcement=validator or equivalent implementation binding metadata',
        failure_evidence=['declaration_node', 'implementation_ref', 'missing_or_incompatible_implementation', 'declaration_location'],
    ),
    TemplateContract(
        family_id='binding',
        template_id='emitted_identity_roundtrip',
        question='Does implementation output round-trip to the declaring rule or node?',
        selector='implementations/validators that emit rule_ids or node_ids',
        traversal='declaration -> implementation -> emitted identity -> declaration index',
        invariant='emitted identity resolves back to the same declaring rule/node',
        auto_capture='a new node is included if its implementation declares emitted identities in standard metadata',
        failure_evidence=['declaration_id', 'implementation_id', 'emitted_identity', 'expected_identity', 'actual_resolved_target'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]
