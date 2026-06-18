# Phase: GREEN
# Layer: backend.domain
"""WMBT-level cohesion / coupling metric for wagon separability (#1147).

Builds ONE undirected graph over WMBTs where an edge connects two WMBTs that
share at least ``min_shared`` salient tokens. On that single graph:

  cohesion(W)    = # edges with BOTH endpoints inside wagon W
  coupling(W, N) = # edges with one endpoint in W and the other in N

Both are in the same unit (edge counts), so separability is a fair comparison:

  separable(W)   <=>  cohesion(W) >= max over neighbors N of coupling(W, N)

DESIGN NOTE: the GRAPH MATH below (edge construction + counting) is exact and
unit-tested. TOKEN EXTRACTION (which words count as salient, ``min_shared``)
is a *calibration knob* (issue #1147 Phase 3), deliberately kept out of the
math so the metric's correctness is independent of vocabulary tuning.
"""
from __future__ import annotations

from itertools import combinations
from typing import Dict, FrozenSet, Optional, Set, Tuple

Edge = FrozenSet[str]


def build_edges(wmbt_tokens: Dict[str, Set[str]], min_shared: int = 1) -> Set[Edge]:
    """Undirected edge {i, j} whenever WMBTs i and j share >= min_shared tokens."""
    edges: Set[Edge] = set()
    for (i, ti), (j, tj) in combinations(sorted(wmbt_tokens.items()), 2):
        if len(ti & tj) >= min_shared:
            edges.add(frozenset((i, j)))
    return edges


def cohesion(members: Set[str], edges: Set[Edge]) -> int:
    """# edges with BOTH endpoints in ``members`` (intra-wagon)."""
    return sum(1 for e in edges if e <= members)


def coupling(a: Set[str], b: Set[str], edges: Set[Edge]) -> int:
    """# edges with exactly one endpoint in ``a`` and one in ``b`` (cross-wagon)."""
    return sum(1 for e in edges if len(e & a) == 1 and len(e & b) == 1)


def cohesion_density(members: Set[str], edges: Set[Edge]) -> float:
    """Intra-wagon edges / max possible (|W| choose 2). Size-invariant in [0,1]."""
    n = len(members)
    max_edges = n * (n - 1) // 2
    return cohesion(members, edges) / max_edges if max_edges else 0.0


def coupling_density(a: Set[str], b: Set[str], edges: Set[Edge]) -> float:
    """Cross edges / max possible (|a| * |b|). Size-invariant in [0,1]."""
    max_edges = len(a) * len(b)
    return coupling(a, b, edges) / max_edges if max_edges else 0.0


def separable(
    wagon: str,
    wagon_members: Dict[str, Set[str]],
    edges: Set[Edge],
) -> Tuple[bool, float, float, Optional[str]]:
    """Return (is_separable, cohesion_density, tightest_coupling_density, neighbor).

    A wagon is separable iff its internal edge DENSITY is at least its tightest
    coupling density to any single neighbor (the MERGE-rule inverse, size-invariant
    so a large wagon is not penalised for having more raw edges).
    """
    members = wagon_members[wagon]
    coh_d = cohesion_density(members, edges)
    best_coupling = 0.0
    best_neighbor: Optional[str] = None
    for other, other_members in wagon_members.items():
        if other == wagon:
            continue
        cd = coupling_density(members, other_members, edges)
        if cd > best_coupling:
            best_coupling, best_neighbor = cd, other
    return (coh_d >= best_coupling, coh_d, best_coupling, best_neighbor)
