# URN: test:atdd-plan:decomposition-protocol:nodes-present
# Acceptance: the planner decomposition-protocol convention-nodes exist and carry the protocol's concepts
# Issue: #761
# Phase: GREEN
# Layer: unit
# Assertion: structural
"""#761 — the decomposition-protocol convention-node(s) exist under
planner/conventions/nodes/ and collectively encode the protocol concepts
(JTBD/ODI grammar, keep/pivot/kill, canonical steps, train-journey,
natural-language normalization, document-trouble obligation, wagon-rationale,
domain-vs-technology, local scope). Guidance-kind nodes; no validator binds.
"""
from __future__ import annotations

import glob
from pathlib import Path

import yaml

_NODES = Path(__file__).resolve().parents[2] / "conventions" / "nodes"
_PREFIX = "planner.decomposition."
_ALLOWED_KINDS = {"principle", "pattern", "constraint"}


def _load_nodes():
    nodes = {}
    for f in glob.glob(str(_NODES / f"{_PREFIX}*.convention.yaml")):
        nodes[Path(f).name] = yaml.safe_load(Path(f).read_text(encoding="utf-8"))
    return nodes


def _corpus(nodes):
    return " ".join(yaml.safe_dump(n) for n in nodes.values()).lower()


def test_decomposition_nodes_exist_and_are_guidance_kind():
    nodes = _load_nodes()
    assert nodes, "no planner.decomposition.* convention-nodes found"
    for name, node in nodes.items():
        assert node["rule_id"].startswith(_PREFIX), name
        assert node["kind"] in _ALLOWED_KINDS, f"{name}: kind {node['kind']!r} not guidance-kind"


def test_two_grammar_distinction_present():
    text = _corpus(_load_nodes())
    assert "jtbd" in text and "odi" in text
    assert "object_of_control" in text  # ODI field
    # JTBD invalid-vs-valid framing: the redis/implementation reframe example
    assert "verb + object" in text or "verb +" in text


def test_keep_pivot_kill_present():
    text = _corpus(_load_nodes())
    for token in ("keep", "pivot", "kill"):
        assert token in text, token


def test_canonical_steps_enumerated():
    text = _corpus(_load_nodes())
    for step in ("define", "locate", "prepare", "confirm", "execute",
                 "monitor", "modify", "resolve", "conclude"):
        assert step in text, step


def test_protocol_obligations_present():
    text = _corpus(_load_nodes())
    assert "normaliz" in text               # natural-language normalization
    assert "document" in text               # document-trouble obligation
    assert "boundary" in text or "rationale" in text  # wagon-rationale discipline
    assert "technology" in text             # domain-vs-technology
    assert "scope" in text                  # local scope
    assert "train" in text                  # train-journey decomposition
