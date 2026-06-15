# URN: test:author-atdd-substrate:substrate-spine:D001-SMOKE-001-schemas-load-and-validate
# Acceptance: acc:author-atdd-substrate:D001-SMOKE-001-schemas-load-and-validate
# WMBT: wmbt:author-atdd-substrate:D001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""D001-SMOKE-001 — the four schemas load from disk and validate a known-good fixture."""
from __future__ import annotations

from jsonschema import validate

from atdd.planner.commands.author_schemas import load_schema

_FIXTURES = {
    "convention-node": {
        "schema_version": "1.0.0", "rule_id": "coder.green.component-urn-marker-is",
        "kind": "rule", "status": "active", "statement": "x",
        "terms": [{"term_id": "urn_marker", "text": "y"}],
    },
    "relationship": {
        "source_ref": "coder.green.a#t", "type": "enables", "target_ref": "coder.green.b",
        "foundation": "finish_to_start", "constraint": "mandatory",
        "control": "internal", "strength": "critical",
    },
    "scope": {
        "scope_id": "scope.source.python", "artifact_kind": "source_file",
        "runtime": "python", "platform": "local_fs",
        "selectors": [{"type": "path_glob", "value": "src/**/*.py"}],
    },
    "gate": {
        "gate_id": "gate.post_commit.local_feedback",
        "trigger": {"type": "git_hook", "name": "post-commit"},
        "selection": {"strategy": "blast_radius"},
        "on_violation": {"action": "never_block"},
        "exit": {"success_code": 0, "failure_code": 0},
    },
}


def test_each_schema_validates_its_fixture():
    for kind, fixture in _FIXTURES.items():
        schema = load_schema(kind)  # real load from disk
        validate(instance=fixture, schema=schema)  # raises on mismatch
