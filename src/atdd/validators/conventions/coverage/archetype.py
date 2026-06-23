"""Reusable graph-question archetype for the `coverage` family (#1204)."""
from __future__ import annotations

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='coverage',
        template_id='reachability_no_orphan',
        question='Is every required node reachable from a valid root or owner?',
        selector='nodes where requires_reachability != false',
        traversal='root nodes -> allowed edges -> reachable set',
        invariant='eligible node is in reachable set',
        auto_capture='a new node is included if its kind/package requires reachability by default',
        failure_evidence=['orphan_node', 'expected_root', 'allowed_paths', 'node_location'],
    ),
    TemplateContract(
        family_id='coverage',
        template_id='source_has_required_target',
        question='For every source node of type X, does required downstream target Y exist?',
        selector='nodes where node.coverage.requires exists',
        traversal='source node -> required relationship/path -> target node set',
        invariant='target set is non-empty and satisfies required target kind/filter',
        auto_capture='a new node is included if it declares coverage requirements',
        failure_evidence=['source_node', 'required_target_kind', 'required_path', 'actual_targets'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]
