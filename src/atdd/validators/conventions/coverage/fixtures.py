"""Canonical valid/invalid graph fragments for the `coverage` family (#1212).

REAL-graph fragments: each builder returns a small ``ConventionGraph`` of real
``Node`` objects (not dict fixtures), so the same evaluators that run over the
composed repo graph run over these. ``hierarchy_coverage`` is pure in-graph, so
it is the variant exercised here; ``wmbt_has_smoke_acceptance`` (inline
suppression markers) and ``no_orphan_nodes`` (relationship-graph files) read real
sources via ``graph.root`` and are covered by the fault-injection parity tests.
"""
from __future__ import annotations

from .._support.graph_loader import ConventionGraph, Node


def _graph(*nodes: Node) -> ConventionGraph:
    g = ConventionGraph()
    for n in nodes:
        g._add(n)
    return g


def valid_hierarchy() -> ConventionGraph:
    """train -> wagon -> feature -> wmbt(+acceptance): every leg satisfied."""
    return _graph(
        Node(id='train:0001', kind='train', location='plan/_trains/0001.yaml',
             refs=['wagon:w']),
        Node(id='wagon:w', kind='wagon', location='plan/w/_w.yaml', package='w',
             refs=['feature:w:f']),
        Node(id='feature:w:f', kind='feature', location='plan/w/features/f.yaml',
             package='w', refs=['wmbt:w:E001']),
        Node(id='wmbt:w:E001', kind='wmbt', location='plan/w/E001.yaml', package='w',
             fields={'acceptances': [{'identity': {'urn': 'acc:w:E001-UNIT-001'}}]}),
    )


def invalid_hierarchy() -> ConventionGraph:
    """One fault per leg: wagon not in any train, wagon with no feature, feature
    with no wmbt, wmbt with no acceptance."""
    return _graph(
        # train references only wagon:w-ok; wagon:w-orphan is in no train
        Node(id='train:0001', kind='train', location='plan/_trains/0001.yaml',
             refs=['wagon:w-ok']),
        Node(id='wagon:w-ok', kind='wagon', location='plan/wok/_wok.yaml', package='wok',
             refs=['feature:wok:f']),
        Node(id='wagon:w-orphan', kind='wagon', location='plan/worph/_worph.yaml',
             package='worph', refs=[]),                       # no feature + no train
        Node(id='feature:wok:f', kind='feature', location='plan/wok/features/f.yaml',
             package='wok', refs=[]),                         # no wmbt
        Node(id='wmbt:wok:E001', kind='wmbt', location='plan/wok/E001.yaml',
             package='wok', fields={'acceptances': []}),      # no acceptance
    )


# Mapping kept for discoverability / parity tooling. Real-graph builders, not dicts.
VALID_FRAGMENTS = {
    'hierarchy_coverage': valid_hierarchy,
}
INVALID_FRAGMENTS = {
    'hierarchy_coverage': invalid_hierarchy,
}
