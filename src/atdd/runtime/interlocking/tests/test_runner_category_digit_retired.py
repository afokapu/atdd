# URN: test:atdd-runtime:interlocking-runner:category-digit-retired
# Issue: #1440 (follows #1421)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1440 — the runtime route-control layer carries NO category digit.

``InterlockingRunner._validate_selected_route`` holds a second, verbatim copy of
the defect #1421 set out to kill: it derives a category from character 2 of the
``train_id`` and compares ``route.category_digit``. A typed
``train:<subject>:<slug>`` has no such digit, so a sound migrated interlocking
cannot be resolved at all — and the route-control trace still publishes a
``route_category_digit`` field that no longer means anything.

These tests resolve a typed, digit-free interlocking end to end and pin the trace
contract to the ``category`` FIELD.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.planner.interlocking.tests.test_category_digit_retired import (
    typed_interlocking_doc,
    write_typed_tree,
)
from atdd.runtime.interlocking import (
    InterlockingResolution,
    InterlockingResolutionError,
    InterlockingRunner,
)


@pytest.fixture()
def typed_il_path(tmp_path: Path) -> Path:
    return write_typed_tree(tmp_path)


def test_resolve_train_resolves_a_typed_digit_free_interlocking(typed_il_path: Path):
    """The runner must resolve a migrated interlocking — today it cannot."""
    runner = InterlockingRunner(typed_il_path)

    res = runner.resolve_train("resolve_match", {"all_players_voted": True})

    assert isinstance(res, InterlockingResolution)
    assert res.route_id == "nominal-all-voted"
    assert res.train_id == "train:match-resolution:standard"
    assert res.category == "nominal"


def test_resolution_carries_no_category_digit(typed_il_path: Path):
    res = InterlockingRunner(typed_il_path).resolve_train(
        "resolve_match", {"all_players_voted": True}
    )
    assert not hasattr(res, "category_digit")


def test_route_control_trace_publishes_category_not_a_digit(typed_il_path: Path):
    trace = InterlockingRunner(typed_il_path).resolve_train(
        "resolve_match", {"all_players_voted": True}
    ).as_trace()

    assert trace["route_category"] == "nominal"
    assert "route_category_digit" not in trace


def test_resolve_train_fails_closed_on_category_field_mismatch(tmp_path: Path):
    """Fail-closed still holds — now judged on the train's ``category`` FIELD."""
    doc = typed_interlocking_doc()
    doc["routes"][0]["category"] = "exception"  # target train declares `nominal`
    il_path = write_typed_tree(tmp_path, doc)

    runner = InterlockingRunner(il_path)
    with pytest.raises(InterlockingResolutionError):
        runner.resolve_train("resolve_match", {"all_players_voted": True})
