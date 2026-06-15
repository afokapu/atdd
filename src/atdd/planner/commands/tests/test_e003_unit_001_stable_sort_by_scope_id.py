# URN: test:author-atdd-substrate:author-scope:E003-UNIT-001-stable-sort-by-scope-id
# Acceptance: acc:author-atdd-substrate:E003-UNIT-001-stable-sort-by-scope-id
# WMBT: wmbt:author-atdd-substrate:E003
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E003-UNIT-001 — a per-file scope embeds its selectors, sorted by selector_id."""
from __future__ import annotations

import yaml

from atdd.planner.commands.author_registry import write_scope


def _sel(sid):
    return {"selector_id": sid, "type": "path_glob", "include": ["src/**/*.py"]}


def test_scope_file_has_sorted_selectors(tmp_path):
    path = tmp_path / "scope.source.python.scope.yaml"
    write_scope({
        "scope_id": "scope.source.python", "artifact_kind": "source_file",
        "selectors": [_sel("selector.source.python.zzz"), _sel("selector.source.python.aaa")],
    }, path)
    doc = yaml.safe_load(path.read_text())
    assert doc["scope_id"] == "scope.source.python"
    assert [s["selector_id"] for s in doc["selectors"]] == [
        "selector.source.python.aaa", "selector.source.python.zzz"]
