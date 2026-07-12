"""Semantic validation tests for validate_interlocking (#1248)."""
from __future__ import annotations

import copy

from atdd.planner.interlocking import load_interlocking, validate_interlocking
from atdd.planner.interlocking.tests._fixtures import interlocking_doc, write_tree


def _rule_ids(violations):
    return {v.rule_id for v in violations}


def test_valid_interlocking_has_no_violations(tmp_path):
    il = load_interlocking(write_tree(tmp_path))
    assert validate_interlocking(il, tmp_path) == []


def test_message_endpoint_must_be_a_declared_lifeline(tmp_path):
    doc = copy.deepcopy(interlocking_doc())
    doc["messages"][0]["to"] = "wagon:ghost"  # not in lifelines
    il = load_interlocking(write_tree(tmp_path, doc))
    violations = validate_interlocking(il, tmp_path)
    assert violations
    assert any("lifeline" in v.detail.lower() for v in violations)


def test_boundary_message_requires_from_neq_to(tmp_path):
    doc = copy.deepcopy(interlocking_doc())
    doc["messages"][0]["from"] = "wagon:player"
    doc["messages"][0]["to"] = "wagon:player"  # boundary but from == to
    il = load_interlocking(write_tree(tmp_path, doc))
    violations = validate_interlocking(il, tmp_path)
    assert any("boundary" in v.detail.lower() for v in violations)


def test_self_message_requires_from_eq_to(tmp_path):
    doc = copy.deepcopy(interlocking_doc())
    doc["messages"][1]["to"] = "wagon:player"  # self message but from != to
    il = load_interlocking(write_tree(tmp_path, doc))
    violations = validate_interlocking(il, tmp_path)
    assert any("self" in v.detail.lower() for v in violations)


def test_route_guard_ref_must_exist(tmp_path):
    doc = copy.deepcopy(interlocking_doc())
    doc["routes"][0]["guard_ref"] = "guard:does-not-exist"
    il = load_interlocking(write_tree(tmp_path, doc))
    violations = validate_interlocking(il, tmp_path)
    assert any("guard" in v.detail.lower() for v in violations)


def test_route_category_must_agree_with_target_train(tmp_path):
    # The target train declares `nominal`; the route claiming `exception` disagrees.
    # Judged against the train's `category` FIELD (#1421), never a parsed identity.
    doc = copy.deepcopy(interlocking_doc())
    doc["routes"][0]["category"] = "exception"
    il = load_interlocking(write_tree(tmp_path, doc))
    violations = validate_interlocking(il, tmp_path)
    assert any("category" in v.detail.lower() for v in violations)


def test_route_must_reference_existing_train(tmp_path):
    doc = copy.deepcopy(interlocking_doc())
    doc["routes"][0]["train_id"] = "train:match-resolution:missing"
    doc["routes"][0]["train_path"] = "plan/_trains/match-resolution/missing.yaml"
    il = load_interlocking(write_tree(tmp_path, doc))
    violations = validate_interlocking(il, tmp_path)
    assert any("train" in v.detail.lower() for v in violations)


def test_violations_are_structured_records(tmp_path):
    doc = copy.deepcopy(interlocking_doc())
    doc["routes"][0]["guard_ref"] = "guard:nope"
    il = load_interlocking(write_tree(tmp_path, doc))
    violations = validate_interlocking(il, tmp_path)
    assert violations
    v = violations[0]
    assert v.rule_id
    assert 1 <= v.severity <= 5
    assert v.location
