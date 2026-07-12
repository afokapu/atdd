"""Canonical valid/invalid REAL-graph fragments for the `sizing` family (#1206/#1212).

Fragments are small ``ConventionGraph`` objects built from real ``Node`` objects —
the same substrate as the composed repo graph — so the sizing evaluators run against
them unchanged (no dict-fixture path). Each variant gets a VALID fragment (evaluates
to ``[]``) and an INVALID fragment (evaluates to a non-empty advisory finding).
"""
from __future__ import annotations

from typing import List

from .._support.graph_loader import ConventionGraph, Node


def _graph(nodes: List[Node]) -> ConventionGraph:
    g = ConventionGraph()
    for n in nodes:
        g._add(n)
    return g


def _wagon(slug: str, produce=None, consume=None) -> Node:
    fields = {
        "wagon": slug,
        "produce": [{"name": n, "contract": None, "telemetry": None} for n in (produce or [])],
        "consume": [{"name": n, "contract": None, "telemetry": None} for n in (consume or [])],
    }
    return Node(id=f"wagon:{slug}", kind="wagon",
                location=f"plan/{slug}/_{slug}.yaml", package=slug, fields=fields)


def _wmbt(wagon: str, code: str, tokens: List[str]) -> Node:
    text = " ".join(tokens)
    return Node(id=f"wmbt:{wagon}:{code}", kind="wmbt",
                location=f"plan/{wagon}/{code}.yaml", package=wagon,
                fields={"object_of_control": text, "statement": ""})


# --- wagon_coupling_complexity ----------------------------------------------
# VALID: two wagons mutually coupled => fan_in=1, fan_out=1, complexity=1 (< threshold).
_COUPLING_VALID = _graph([
    _wagon("alpha", produce=["x"], consume=["y"]),
    _wagon("beta", produce=["y"], consume=["x"]),
])

# INVALID: a hub consuming 3 distinct producers (fan_in=3) AND consumed by 3 distinct
# wagons (fan_out=3) => complexity = 9 (> default threshold 6).
_COUPLING_INVALID = _graph([
    _wagon("hub", produce=["H"], consume=["a", "b", "c"]),
    _wagon("pa", produce=["a"]),
    _wagon("pb", produce=["b"]),
    _wagon("pc", produce=["c"]),
    _wagon("c1", consume=["H"]),
    _wagon("c2", consume=["H"]),
    _wagon("c3", consume=["H"]),
])


# --- wagon_separability -----------------------------------------------------
# Salient tokens must be >= 4 chars (the token filter); these are nonce words.
# VALID: one cohesive wagon (every WMBT shares 'alpha'/'beta1'), no neighbor => separable.
_SEP_VALID = _graph([
    _wmbt("w1", "A", ["alpha", "beta1", "gamma"]),
    _wmbt("w1", "B", ["alpha", "beta1", "delta"]),
    _wmbt("w1", "C", ["alpha", "beta1", "echo1"]),
])

# INVALID: w3's WMBTs share NOTHING internally but each pairs with a distinct w1
# member (cohesion 0 < coupling) => w3 flagged [MERGE]; cohesive w1 is NOT flagged.
_SEP_INVALID = _graph([
    _wmbt("w1", "A", ["alpha", "pear1"]),
    _wmbt("w1", "B", ["alpha", "quil1"]),
    _wmbt("w1", "C", ["alpha", "rave1"]),
    _wmbt("w3", "X", ["pear1", "sand1"]),
    _wmbt("w3", "Y", ["quil1", "tin1x"]),
    _wmbt("w3", "Z", ["rave1", "urns1"]),
])


# Evaluation config per variant (fixtures use explicit calibration, not repo config).
FIXTURE_CONFIG = {
    "wagon_coupling_complexity": {"variant": "wagon_coupling_complexity", "threshold": 6},
    "wagon_separability": {"variant": "wagon_separability", "min_shared": 1, "min_size": 3},
}

VALID_FRAGMENTS = {
    "wagon_coupling_complexity": _COUPLING_VALID,
    "wagon_separability": _SEP_VALID,
}

INVALID_FRAGMENTS = {
    "wagon_coupling_complexity": _COUPLING_INVALID,
    "wagon_separability": _SEP_INVALID,
}
