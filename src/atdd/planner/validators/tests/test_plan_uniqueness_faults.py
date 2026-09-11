# Purpose: prove test_train_ids_are_unique actually reads the registry it is
# handed, by feeding it a fixture shape that carries a duplicate.
"""Fault injection for SPEC-PLATFORM-UNIQUE-0002 (#1915).

The check ran over `trains_registry.get("trains", [])`, but the fixture returns
`{theme: [entry, ...]}` — no `"trains"` key — so it iterated an empty list and
reported PASS across every one of the 21 registered trains. A validator that
cannot fail is not a validator; these tests hold it to the fixture's real shape.
"""
import pytest

# Aliased on import: a bare `test_`-prefixed name would be re-collected here and
# run a SECOND time against the real repo fixture, which is not what this file is for.
from atdd.planner.validators.test_plan_uniqueness import (
    test_train_ids_are_unique as assert_train_ids_unique,
)


def _entry(train_id, path):
    return {"train_id": train_id, "description": "", "path": path, "wagons": []}


def test_duplicate_train_id_within_a_theme_is_detected():
    registry = {
        "issue-lifecycle": [
            _entry("train:issue-lifecycle:demo", "plan/_trains/issue-lifecycle/demo.yaml"),
            _entry("train:issue-lifecycle:demo", "plan/_trains/issue-lifecycle/demo.yaml"),
        ]
    }
    with pytest.raises(AssertionError, match="train:issue-lifecycle:demo"):
        assert_train_ids_unique(registry)


def test_the_same_train_id_in_two_themes_is_detected():
    """The category-pivot fork lands in a different bucket, not a different row.

    A per-theme check would pass this. The registry is one namespace, so the
    count has to span it.
    """
    registry = {
        "issue-lifecycle": [_entry("train:issue-lifecycle:pivot", "plan/_trains/issue-lifecycle/pivot.yaml")],
        "substrate": [_entry("train:issue-lifecycle:pivot", "plan/_trains/issue-lifecycle/pivot.yaml")],
    }
    with pytest.raises(AssertionError, match="2 occurrences"):
        assert_train_ids_unique(registry)


def test_a_clean_registry_passes():
    registry = {
        "issue-lifecycle": [_entry("train:issue-lifecycle:a", "plan/_trains/issue-lifecycle/a.yaml")],
        "substrate": [_entry("train:substrate:b", "plan/_trains/substrate/b.yaml")],
    }
    assert_train_ids_unique(registry)


def test_an_empty_registry_passes_without_crashing():
    assert_train_ids_unique({"commons": [], "substrate": []})
