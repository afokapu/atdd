# URN: test:author-atdd-substrate:author-scope:E003-UNIT-002-idempotent-atomic
# Acceptance: acc:author-atdd-substrate:E003-UNIT-002-idempotent-atomic
# WMBT: wmbt:author-atdd-substrate:E003
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E003-UNIT-002 — re-inserting an identical scope is a no-op (atomic)."""
from __future__ import annotations

import yaml

from atdd.planner.commands.author_registry import insert_scope


def _scope():
    return {"scope_id": "scope.source.python", "artifact_kind": "source_file",
            "selectors": [{"type": "path_glob", "value": "src/**/*.py"}]}


def test_reinsert_scope_noop(tmp_path):
    path = tmp_path / "scopes.yaml"
    insert_scope(_scope(), path)
    first = path.read_text()
    insert_scope(_scope(), path)
    second = path.read_text()
    assert first == second
    assert len(yaml.safe_load(second)["scopes"]) == 1
