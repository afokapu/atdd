"""Reusable graph-question archetype for the `presence` family (#1204)."""
from __future__ import annotations

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='presence',
        template_id='required_field_presence',
        question='Does every eligible node declare the fields required by its convention/schema?',
        selector='nodes whose schema/kind declares required fields',
        traversal='node -> required_fields',
        invariant='every required field exists and is non-empty',
        auto_capture='a new node is included if its schema/kind declares required fields',
        failure_evidence=['node_id', 'missing_field', 'schema_id', 'node_location'],
    ),
    TemplateContract(
        family_id='presence',
        template_id='required_relationship_presence',
        question='Does every eligible node have a required outgoing relationship or child edge?',
        selector='nodes whose schema/kind declares required relationships',
        traversal='node -> required_relationship_type -> target nodes',
        invariant='required relationship target set is non-empty',
        auto_capture='a new node is included if its schema declares required relationships',
        failure_evidence=['node_id', 'missing_relationship', 'expected_target_kind', 'node_location'],
    ),
    TemplateContract(
        family_id='presence',
        template_id='conditional_requirement',
        question='If condition A is true on a node, does field/edge B exist?',
        selector='nodes declaring conditional requirements',
        traversal='node -> condition field/value -> required field/edge',
        invariant='if condition is true, required target exists',
        auto_capture='a new node is included if its schema declares conditional requirements',
        failure_evidence=['node_id', 'condition', 'missing_requirement', 'node_location'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]
