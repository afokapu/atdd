"""Reusable graph-question archetype for the `grammar` family (#1204)."""
from __future__ import annotations

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='grammar',
        template_id='identifier_grammar_conformance',
        question='Does an identifier, URN, rule id, or node id follow canonical grammar?',
        selector='nodes with id/rule_id/urn/name fields',
        traversal='node -> identifier field -> grammar parser',
        invariant='parser accepts identifier and parsed parts match graph context',
        auto_capture='a new node is included if it declares a grammar-governed identifier field',
        failure_evidence=['node_id', 'field', 'value', 'grammar_name', 'parse_error'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]
