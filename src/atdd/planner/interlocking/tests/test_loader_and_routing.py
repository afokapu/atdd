"""Loader + route resolution tests (#1248)."""
from __future__ import annotations

import copy

import pytest

from atdd.planner.interlocking import (
    RouteResolutionError,
    evaluate_interlocking_route,
    load_interlocking,
    parse_interlocking,
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


# ---------------------------------------------------------------------------
# Obligation resolution (#1546).
#
# `_interlocking_wmbt_surface_or_residual` could not emit partly because it
# compared `residual:*` ids against `wmbt:*` refs — two namespaces that never
# intersect, so the residual check silently matched nothing. These tests pin the
# resolver's behaviour so #1547 can build on it, and each asserts a distinction
# that would vanish if the resolver regressed to a namespace-blind set.
# ---------------------------------------------------------------------------
def test_obligation_index_reports_the_surface_kind_that_carries_each_ref():
    il = parse_interlocking(interlocking_doc())
    index = il.obligation_index()
    assert index["wmbt:pressure-collapse:C001"] == {"invariant"}
    assert index["wmbt:pressure-collapse:E001"] == {"guard", "fragment"}
    assert index["wmbt:pressure-collapse:M001"] == {"residual:structural"}


def test_residual_wmbt_refs_are_wmbt_urns_not_residual_ids():
    """The namespace mismatch that made the coverage rule vacuous."""
    il = parse_interlocking(interlocking_doc())
    refs = il.residual_wmbt_refs()
    assert refs == {"wmbt:pressure-collapse:M001"}
    assert all(r.startswith("wmbt:") for r in refs)
    residual_ids = {r.id for r in il.residuals}
    assert refs.isdisjoint(residual_ids), (
        "residual ids and WMBT refs must never be compared as the same namespace"
    )


def test_obligation_index_is_empty_when_no_surface_declares_a_ref():
    """Guards against a resolver that looks populated on an unreferenced document.

    This is the pre-#1546 state of both authored interlockings: every surface
    present, zero obligations nameable.
    """
    doc = interlocking_doc()
    for msg in doc["messages"]:
        msg.pop("wmbt_refs", None)
    for frag in doc["fragments"]:
        frag.pop("wmbt_refs", None)
        for guard in frag["guards"]:
            guard.pop("wmbt_refs", None)
    for inv in doc["invariants"]:
        inv.pop("wmbt_ref", None)
    for rsd in doc["residuals"]:
        rsd.pop("wmbt_refs", None)
    il = parse_interlocking(doc)
    assert il.obligation_index() == {}
    assert il.residual_wmbt_refs() == set()


def test_self_messages_are_reported_as_their_own_surface_kind():
    doc = interlocking_doc()
    self_msg = next(m for m in doc["messages"] if m["kind"] == "self")
    self_msg["wmbt_refs"] = ["wmbt:pressure-collapse:Y001"]
    il = parse_interlocking(doc)
    assert il.obligation_index()["wmbt:pressure-collapse:Y001"] == {"self"}
