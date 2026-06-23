"""Reusable graph-question archetype for the `schema` family (#1204)."""
from __future__ import annotations

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='schema',
        template_id='node_schema_conformance',
        question='Does each node conform to its declared schema?',
        selector='nodes where node.schema exists',
        traversal='node -> schema_id -> schema document -> validate node payload',
        invariant='jsonschema validation passes',
        auto_capture='a new node is included if it declares `schema`',
        failure_evidence=['node_id', 'schema_id', 'schema_error_path', 'schema_error_message', 'node_location'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]
