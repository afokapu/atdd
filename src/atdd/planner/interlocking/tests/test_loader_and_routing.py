"""Loader + route resolution tests (#1248)."""
from __future__ import annotations

import copy

import pytest

from atdd.planner.interlocking import (
    RouteResolutionError,
    evaluate_interlocking_route,
    load_interlocking,
)
from atdd.planner.interlocking.tests._fixtures import interlocking_doc, write_tree


def test_load_interlocking_returns_typed_model(tmp_path):
    il_path = write_tree(tmp_path)
    il = load_interlocking(il_path)
    assert il.interlocking_id == "interlocking:match-resolution"
    assert il.route_resolution.strategy == "fail_on_multiple_match"
    assert [r.route_id for r in il.routes] == ["nominal-all-voted", "alternate-timeout"]
    assert il.entrypoint.exposed is True
    assert "resolve_match" in il.entrypoint.actions


def test_route_resolution_selects_matching_guard(tmp_path):
    il = load_interlocking(write_tree(tmp_path))
    route_id = evaluate_interlocking_route(
        il, action="resolve_match", inputs={"all_players_voted": True}
    )
    assert route_id == "nominal-all-voted"

    route_id = evaluate_interlocking_route(
        il, action="resolve_match", inputs={"timer_expired": True}
    )
    assert route_id == "alternate-timeout"


def test_fail_on_multiple_match_fails_closed(tmp_path):
    il = load_interlocking(write_tree(tmp_path))
    with pytest.raises(RouteResolutionError):
        evaluate_interlocking_route(
            il,
            action="resolve_match",
            inputs={"all_players_voted": True, "timer_expired": True},
        )


def test_no_match_fails_closed(tmp_path):
    il = load_interlocking(write_tree(tmp_path))
    with pytest.raises(RouteResolutionError):
        evaluate_interlocking_route(il, action="resolve_match", inputs={})


def test_unknown_action_fails_closed(tmp_path):
    il = load_interlocking(write_tree(tmp_path))
    with pytest.raises(RouteResolutionError):
        evaluate_interlocking_route(
            il, action="not_an_action", inputs={"all_players_voted": True}
        )


def test_first_priority_picks_lowest_priority_on_multi_match(tmp_path):
    doc = copy.deepcopy(interlocking_doc())
    doc["route_resolution"]["strategy"] = "first_priority"
    il = load_interlocking(write_tree(tmp_path, doc))
    # both guards true -> first_priority picks priority 10 (nominal) deterministically
    route_id = evaluate_interlocking_route(
        il,
        action="resolve_match",
        inputs={"all_players_voted": True, "timer_expired": True},
    )
    assert route_id == "nominal-all-voted"


def test_first_priority_requires_unique_priorities(tmp_path):
    doc = copy.deepcopy(interlocking_doc())
    doc["route_resolution"]["strategy"] = "first_priority"
    doc["routes"][1]["priority"] = 10  # duplicate of route 0
    il = load_interlocking(write_tree(tmp_path, doc))
    with pytest.raises(RouteResolutionError):
        evaluate_interlocking_route(
            il,
            action="resolve_match",
            inputs={"all_players_voted": True, "timer_expired": True},
        )


def test_state_snapshot_merges_with_inputs(tmp_path):
    il = load_interlocking(write_tree(tmp_path))
    route_id = evaluate_interlocking_route(
        il,
        action="resolve_match",
        inputs={},
        state={"timer_expired": True},
    )
    assert route_id == "alternate-timeout"
