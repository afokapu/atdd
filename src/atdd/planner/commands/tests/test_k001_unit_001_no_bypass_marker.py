# URN: test:author-atdd-substrate:substrate-spine:K001-UNIT-001-no-bypass-marker
# Acceptance: acc:author-atdd-substrate:K001-UNIT-001-no-bypass-marker
# WMBT: wmbt:author-atdd-substrate:K001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""K001-UNIT-001 — authored artifacts carry no authoring-only suppression/bypass marker."""
from __future__ import annotations

from atdd.planner.commands.author import create_convention_node
from atdd.planner.commands.author_registry import insert_gate, insert_relationship, write_scope

_FORBIDDEN = ["atdd:suppress", "skip-permissions", "dangerously", "noqa", "BYPASS", "type: ignore"]


def _author_all(root):
    node = create_convention_node(
        role="coder", rule_id="coder.green.x", statement="s",
        terms=[{"term_id": "t", "text": "y"}], root=root,
    )
    rel = root / "relationships.yaml"
    insert_relationship(
        {"source_ref": "coder.green.a", "type": "enables", "target_ref": "coder.green.b"}, rel)
    scope = root / "scope.source.python.scope.yaml"
    write_scope(
        {"scope_id": "scope.source.python",
         "selectors": [{"selector_id": "selector.source.python.pg", "type": "path_glob", "include": ["x"]}]}, scope)
    gate = root / "post-commit.yaml"
    insert_gate(
        {"gate_id": "gate.post_commit.x", "trigger": {"type": "git_hook", "name": "post-commit"},
         "selection": {"strategy": "blast_radius"}, "on_violation": {"action": "never_block"},
         "exit": {"success_code": 0, "failure_code": 0}}, gate)
    return [node, rel, scope, gate]


def test_no_bypass_marker_in_any_authored_artifact(tmp_path):
    for path in _author_all(tmp_path):
        text = path.read_text()
        for marker in _FORBIDDEN:
            assert marker not in text, f"{path.name} contains forbidden marker {marker!r}"
