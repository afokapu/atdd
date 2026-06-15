# URN: test:author-atdd-substrate:author-scope:E003-UNIT-002-idempotent-atomic
# Acceptance: acc:author-atdd-substrate:E003-UNIT-002-idempotent-atomic
# WMBT: wmbt:author-atdd-substrate:E003
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E003-UNIT-002 — re-adding the same selector to a scope file is a no-op (atomic)."""
from __future__ import annotations

import yaml

from atdd.planner.commands.author_registry import insert_scope_selector


def test_reinsert_selector_noop(tmp_path):
    path = tmp_path / "scope.source.python.scope.yaml"
    meta = {"scope_id": "scope.source.python", "artifact_kind": "source_file"}
    sel = {"selector_id": "selector.source.python.path-glob", "type": "path_glob", "include": ["src/**/*.py"]}
    insert_scope_selector(meta, sel, path)
    first = path.read_text()
    insert_scope_selector(meta, sel, path)
    second = path.read_text()
    assert first == second
    assert len(yaml.safe_load(second)["selectors"]) == 1
