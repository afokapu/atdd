# URN: test:author-atdd-substrate:author-scope:E003-UNIT-001-stable-sort-by-scope-id
# Acceptance: acc:author-atdd-substrate:E003-UNIT-001-stable-sort-by-scope-id
# WMBT: wmbt:author-atdd-substrate:E003
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E003-UNIT-001 — inserting two scopes yields scopes.yaml sorted by scope_id."""
from __future__ import annotations

import yaml

from atdd.planner.commands.author_registry import insert_scope


def _scope(sid):
    return {"scope_id": sid, "artifact_kind": "source_file",
            "selectors": [{"type": "path_glob", "value": "src/**/*.py"}]}


def test_two_scopes_sorted(tmp_path):
    path = tmp_path / "scopes.yaml"
    insert_scope(_scope("scope.source.zzz"), path)
    insert_scope(_scope("scope.source.aaa"), path)
    doc = yaml.safe_load(path.read_text())
    assert [s["scope_id"] for s in doc["scopes"]] == ["scope.source.aaa", "scope.source.zzz"]
