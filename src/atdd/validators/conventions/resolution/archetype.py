"""Reusable graph-question archetype for the `resolution` family (#1204)."""
from __future__ import annotations

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='resolution',
        template_id='direct_reference_resolution',
        question='Does every declared reference resolve to an existing graph target?',
        selector='nodes with refs/node_refs/rule_refs/relationship_targets',
        traversal='source node -> reference value -> target index',
        invariant='target_index.contains(reference)',
        auto_capture='a new node is included if it declares references using standard ref fields',
        failure_evidence=['source_node', 'ref_field', 'missing_ref', 'expected_target_kind', 'source_location'],
    ),
    TemplateContract(
        family_id='resolution',
        template_id='artifact_reference_resolution',
        question='Does every file, schema, fixture, or URN artifact reference resolve to a real artifact?',
        selector='nodes with artifact_refs/file_refs/schema_refs/fixture_refs',
        traversal='node -> artifact reference -> repository artifact index',
        invariant='artifact exists and is addressable from repo root/package root',
        auto_capture='a new node is included if it declares artifact references with standard metadata',
        failure_evidence=['node_id', 'artifact_ref', 'artifact_kind', 'expected_path', 'node_location'],
    ),
    TemplateContract(
        family_id='resolution',
        template_id='reference_chain_resolution',
        question='Does a multi-hop reference chain resolve completely?',
        selector='nodes that declare chained references or transitive dependencies',
        traversal='start node -> ref A -> target node -> ref B -> final target',
        invariant='all hops resolve; no missing intermediate target',
        auto_capture='a new node is included if it declares a chain shape using standard traversal metadata',
        failure_evidence=['start_node', 'chain_path', 'failed_hop', 'missing_ref'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]
