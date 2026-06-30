"""Normalized digest determinism tests (#1248)."""
from __future__ import annotations

import copy

import yaml

from atdd.planner.interlocking import normalized_interlocking_digest
from atdd.planner.interlocking.tests._fixtures import interlocking_doc


def test_digest_is_sha256_hex():
    digest = normalized_interlocking_digest(interlocking_doc())
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_digest_stable_across_irrelevant_formatting():
    doc = interlocking_doc()
    # round-trip through YAML with different key ordering / flow style
    reserialized = yaml.safe_load(yaml.safe_dump(doc, sort_keys=True, default_flow_style=True))
    assert normalized_interlocking_digest(doc) == normalized_interlocking_digest(reserialized)


def test_digest_ignores_its_own_content_digest_field():
    a = interlocking_doc()
    b = copy.deepcopy(a)
    b["source"]["content_digest"] = "a-totally-different-placeholder"
    assert normalized_interlocking_digest(a) == normalized_interlocking_digest(b)


def test_digest_changes_on_semantic_change():
    base = normalized_interlocking_digest(interlocking_doc())

    changed_guard = interlocking_doc()
    changed_guard["fragments"][0]["guards"][0]["expression"] = "all_players_voted == false"
    assert normalized_interlocking_digest(changed_guard) != base

    changed_route = interlocking_doc()
    changed_route["routes"][0]["train_id"] = "3009-something-else"
    assert normalized_interlocking_digest(changed_route) != base

    changed_priority = interlocking_doc()
    changed_priority["routes"][0]["priority"] = 999
    assert normalized_interlocking_digest(changed_priority) != base


def test_digest_is_order_sensitive_for_routes():
    swapped = interlocking_doc()
    swapped["routes"] = list(reversed(swapped["routes"]))
    assert normalized_interlocking_digest(swapped) != normalized_interlocking_digest(
        interlocking_doc()
    )
