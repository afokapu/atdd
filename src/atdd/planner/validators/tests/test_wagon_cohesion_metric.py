"""Unit tests for the WMBT-level cohesion/coupling metric (#1147).

Tests the GRAPH MATH on explicit synthetic token sets — independent of any
real token-extraction vocabulary (which is a calibration knob).
"""
from __future__ import annotations

import pytest

from atdd.planner.validators._wagon_cohesion import (
    build_edges,
    cohesion,
    coupling,
    separable,
)

pytestmark = [pytest.mark.planner]


# W1 = {a,b,c} all share token "x" (cohesive); W2 = {d,e} share "y"; a-d share "cross".
_TOKENS = {
    "a": {"x", "cross"},
    "b": {"x"},
    "c": {"x"},
    "d": {"y", "cross"},
    "e": {"y"},
}
_W1 = {"a", "b", "c"}
_W2 = {"d", "e"}
_MEMBERS = {"w1": _W1, "w2": _W2}


def test_build_edges_shared_token():
    edges = build_edges(_TOKENS, min_shared=1)
    # ab, ac, bc (share x) + de (share y) + ad (share cross) = 5
    assert edges == {
        frozenset({"a", "b"}),
        frozenset({"a", "c"}),
        frozenset({"b", "c"}),
        frozenset({"d", "e"}),
        frozenset({"a", "d"}),
    }


def test_min_shared_raises_threshold():
    # With min_shared=2 only pairs sharing >=2 tokens survive; none here -> no edges.
    assert build_edges(_TOKENS, min_shared=2) == set()


def test_cohesion_counts_intra_edges():
    edges = build_edges(_TOKENS)
    assert cohesion(_W1, edges) == 3   # ab, ac, bc
    assert cohesion(_W2, edges) == 1   # de


def test_coupling_counts_cross_edges():
    edges = build_edges(_TOKENS)
    assert coupling(_W1, _W2, edges) == 1   # a-d only (de is intra-W2, not cross)


def test_separable_when_cohesion_ge_coupling():
    edges = build_edges(_TOKENS)
    sep1, coh1, mc1, nb1 = separable("w1", _MEMBERS, edges)
    assert (coh1, mc1, sep1) == (3, 1, True)
    sep2, coh2, mc2, nb2 = separable("w2", _MEMBERS, edges)
    assert (coh2, mc2, sep2) == (1, 1, True)   # tie counts as separable (>=)


def test_merge_signal_when_coupling_exceeds_cohesion():
    # A 1-WMBT wagon w3={f} that shares tokens with both w1 members but has no
    # internal edge -> cohesion 0, coupling >=1 -> NOT separable (a MERGE signal).
    toks = dict(_TOKENS, f={"x"})            # f shares "x" with a,b,c
    edges = build_edges(toks)
    members = dict(_MEMBERS, w3={"f"})
    sep, coh, mc, nb = separable("w3", members, edges)
    assert coh == 0 and mc >= 1 and sep is False and nb == "w1"
