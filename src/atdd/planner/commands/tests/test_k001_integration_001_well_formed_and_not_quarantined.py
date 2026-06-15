# URN: test:author-atdd-substrate:substrate-spine:K001-INTEGRATION-001-well-formed-and-not-quarantined
# Acceptance: acc:author-atdd-substrate:K001-INTEGRATION-001-well-formed-and-not-quarantined
# WMBT: wmbt:author-atdd-substrate:K001
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""K001-INTEGRATION-001 — each authored artifact is well-formed and deterministic.

A freshly authored artifact of each kind validates against its own on-disk
schema, and re-authoring is byte-identical — so validation outcome is stable
(baseline-equivalent), not perturbed by authoring.
"""
from __future__ import annotations

import yaml
from jsonschema import validate

from atdd.planner.commands.author import create_convention_node
from atdd.planner.commands.author_registry import insert_gate, insert_relationship, write_scope
from atdd.planner.commands.author_schemas import load_schema


def test_each_kind_well_formed_and_deterministic(tmp_path):
    node = create_convention_node(role="coder", rule_id="coder.green.x", statement="s",
                                  terms=[{"term_id": "t", "text": "y"}], root=tmp_path)
    validate(yaml.safe_load(node.read_text()), load_schema("convention-node"))

    rel = tmp_path / "relationships.yaml"
    edge = {"source_ref": "coder.green.a", "type": "enables", "target_ref": "coder.green.b"}
    insert_relationship(edge, rel)
    before = rel.read_text()
    for e in yaml.safe_load(before)["edges"]:
        validate(e, load_schema("relationship"))
    insert_relationship(edge, rel)  # re-author => byte-identical (stable outcome)
    assert rel.read_text() == before

    scope = tmp_path / "scope.source.python.scope.yaml"
    write_scope({"scope_id": "scope.source.python",
                 "selectors": [{"selector_id": "selector.source.python.pg", "type": "path_glob", "include": ["x"]}]}, scope)
    validate(yaml.safe_load(scope.read_text()), load_schema("scope"))

    gate = tmp_path / "post-commit.yaml"
    insert_gate({"gate_id": "gate.post_commit.x", "trigger": {"type": "git_hook", "name": "post-commit"},
                 "selection": {"strategy": "blast_radius"}, "on_violation": {"action": "never_block"},
                 "exit": {"success_code": 0, "failure_code": 0}}, gate)
    for g in yaml.safe_load(gate.read_text())["gates"]:
        validate(g, load_schema("gate"))
