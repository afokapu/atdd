"""Reusable graph-question archetype for the `sizing` family (#1204).

Real-graph execution (#1212): the `cardinality_bounds` template is instantiated by
two advisory wagon-sizing variants that run over the REAL composed convention graph
(``ConventionGraph`` of ``Node`` objects), parameterized by ``config['variant']``:

  - wagon_coupling_complexity : fan_in * fan_out (Henry-Kafura proxy) over the
        produce->consume artifact-NAME graph vs a soft threshold.
  - wagon_separability        : WMBT token-cohesion density vs the tightest
        single-neighbor coupling density (the MERGE-rule inverse).

The metric math is reimplemented self-contained here (not imported from the legacy
planner validators, which #1212 decommissions); faithfulness is PROVEN by the
variant tests, which assert the convention evaluator flags the identical wagon set
as the legacy validator on the live corpus.
"""
from __future__ import annotations

import logging

import re
from itertools import combinations
from typing import Dict, List, Optional, Set, Tuple

import yaml

from .._support.template_contract import TemplateContract

_log = logging.getLogger(__name__)

TEMPLATES = [
    TemplateContract(
        family_id='sizing',
        template_id='cardinality_bounds',
        question='Is the number of related nodes within allowed min/max bounds?',
        selector='nodes or scopes with declared cardinality constraints',
        traversal='source/scope -> collect related nodes -> count',
        invariant='min <= count <= max',
        auto_capture='a new node is included if it declares cardinality constraints',
        failure_evidence=['source_node_or_scope', 'relationship', 'actual_count', 'min', 'max', 'targets'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]


# --- shared config reader ---------------------------------------------------
def _wagon_config(root, key: str, default: int) -> int:
    """Soft calibration knob from .atdd/config.yaml (planner.wagon.<key>), matching
    the legacy validators' config surface so live behavior is identical."""
    try:
        cfg = yaml.safe_load((root / ".atdd" / "config.yaml").read_text()) or {}
        val = ((cfg.get("planner") or {}).get("wagon") or {}).get(key)
        return int(val) if val is not None else default
    except Exception as exc:
        _log.debug("convention evaluator handled a recoverable error", extra={"error": str(exc)[:160]})
        return default


# --- variant 1: wagon_coupling_complexity -----------------------------------
_DEFAULT_COUPLING_THRESHOLD = 6


def _wagon_io(graph) -> Dict[str, Dict[str, list]]:
    """wagon-name -> {'produce': [names], 'consume': [names]} from the real wagon nodes.

    Keyed on the artifact NAME (never the nullable contract), matching legacy
    ``load_manifests`` exactly.
    """
    out: Dict[str, Dict[str, list]] = {}
    for w in graph.by_kind("wagon"):
        d = w.fields
        wagon = d.get("wagon") or str(d.get("urn", "")).split(":")[-1]
        if not wagon:
            continue
        prod = [p["name"] for p in (d.get("produce") or []) if isinstance(p, dict) and p.get("name")]
        cons = [c["name"] for c in (d.get("consume") or []) if isinstance(c, dict) and c.get("name")]
        out[wagon] = {"produce": prod, "consume": cons}
    return out


def _coupling_edges(manifests: Dict[str, Dict[str, list]]) -> Dict[str, set]:
    """producer-wagon -> {consumer-wagons} via shared artifact NAME (legacy build_edges)."""
    producers: Dict[str, str] = {}
    for w, io in manifests.items():
        for name in io.get("produce", []):
            producers[name] = w
    edges: Dict[str, set] = {w: set() for w in manifests}
    for w, io in manifests.items():
        for name in io.get("consume", []):
            pw = producers.get(name)
            if pw and pw != w:
                edges[pw].add(w)
    return edges


def compute_coupling(manifests: Dict[str, Dict[str, list]]) -> Dict[str, Tuple[int, int, int, set, set]]:
    """wagon -> (fan_in, fan_out, complexity, consumers, producers)."""
    edges = _coupling_edges(manifests)
    fan_out = {w: edges.get(w, set()) for w in manifests}
    fan_in: Dict[str, set] = {w: set() for w in manifests}
    for producer, consumers in edges.items():
        for consumer in consumers:
            fan_in.setdefault(consumer, set()).add(producer)
    result = {}
    for w in manifests:
        fi, fo = fan_in.get(w, set()), fan_out.get(w, set())
        result[w] = (len(fi), len(fo), len(fi) * len(fo), set(fo), set(fi))
    return result


def evaluate_coupling_complexity(graph, config=None) -> List[dict]:
    """Flag wagons whose coupling complexity (fan_in * fan_out) exceeds the soft threshold."""
    config = config or {}
    threshold = config.get("threshold")
    if threshold is None:
        threshold = _wagon_config(graph.root, "coupling_complexity_threshold", _DEFAULT_COUPLING_THRESHOLD)
    out: List[dict] = []
    for wagon, (fan_in, fan_out, cx, consumers, producers) in sorted(compute_coupling(_wagon_io(graph)).items()):
        if cx > threshold:
            out.append({
                "source_node_or_scope": f"wagon:{wagon}",
                "relationship": f"coupling-complexity fan_in({fan_in})*fan_out({fan_out})",
                "actual_count": cx,
                "max": threshold,
                "targets": sorted(consumers | producers),
            })
    return out


# --- variant 2: wagon_separability ------------------------------------------
_DEFAULT_MIN_SHARED = 3
_DEFAULT_MIN_SIZE = 3
_STOP = {
    "when", "with", "that", "this", "into", "from", "than", "then", "they", "them",
    "their", "were", "will", "must", "every", "each", "because", "which", "while",
    "where", "what", "does", "not", "and", "for", "the", "via", "per", "without",
    "after", "before", "during", "over", "under", "across", "being", "have", "has",
}


def wmbt_salient_tokens(text: str) -> Set[str]:
    words = re.split(r"[-_\s:.,/()]+", (text or "").lower())
    return {w for w in words if len(w) >= 4 and w not in _STOP}


def _wmbts_by_wagon(graph) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """(wmbt_tokens {gid: tokens}, wagon_members {wagon: {gid}}). gid = wagon:stem.

    Wagon is taken from the WMBT urn's wagon component (urn.split(':')[1]) and the
    member id from the source-file stem, matching legacy ``load_wmbts_by_wagon``.
    """
    wmbt_tokens: Dict[str, Set[str]] = {}
    wagon_members: Dict[str, Set[str]] = {}
    for n in graph.by_kind("wmbt"):
        urn = str(n.id)
        if not urn.startswith("wmbt:"):
            continue
        wagon = urn.split(":")[1]
        stem = n.location.rsplit("/", 1)[-1].removesuffix(".yaml")
        gid = f"{wagon}:{stem}"
        wmbt_tokens[gid] = wmbt_salient_tokens(
            f"{n.fields.get('object_of_control', '')} {n.fields.get('statement', '')}"
        )
        wagon_members.setdefault(wagon, set()).add(gid)
    return wmbt_tokens, wagon_members


def _token_edges(wmbt_tokens: Dict[str, Set[str]], min_shared: int):
    edges = set()
    for (i, ti), (j, tj) in combinations(sorted(wmbt_tokens.items()), 2):
        if len(ti & tj) >= min_shared:
            edges.add(frozenset((i, j)))
    return edges


def _cohesion_density(members: Set[str], edges) -> float:
    n = len(members)
    max_edges = n * (n - 1) // 2
    intra = sum(1 for e in edges if e <= members)
    return intra / max_edges if max_edges else 0.0


def _coupling_density(a: Set[str], b: Set[str], edges) -> float:
    max_edges = len(a) * len(b)
    cross = sum(1 for e in edges if len(e & a) == 1 and len(e & b) == 1)
    return cross / max_edges if max_edges else 0.0


def _separable(wagon: str, wagon_members: Dict[str, Set[str]], edges) -> Tuple[bool, float, float, Optional[str]]:
    members = wagon_members[wagon]
    coh_d = _cohesion_density(members, edges)
    best_coupling, best_neighbor = 0.0, None
    for other, other_members in wagon_members.items():
        if other == wagon:
            continue
        cd = _coupling_density(members, other_members, edges)
        if cd > best_coupling:
            best_coupling, best_neighbor = cd, other
    return (coh_d >= best_coupling, coh_d, best_coupling, best_neighbor)


def evaluate_separability(graph, config=None) -> List[dict]:
    """Flag wagons (>= min_size WMBTs) whose internal cohesion density is below the
    tightest single-neighbor coupling density — the advisory [MERGE] signal."""
    config = config or {}
    min_shared = config.get("min_shared")
    if min_shared is None:
        min_shared = _wagon_config(graph.root, "separability_min_shared", _DEFAULT_MIN_SHARED)
    min_size = config.get("min_size")
    if min_size is None:
        min_size = _wagon_config(graph.root, "separability_min_graph_size", _DEFAULT_MIN_SIZE)

    wmbt_tokens, wagon_members = _wmbts_by_wagon(graph)
    edges = _token_edges(wmbt_tokens, min_shared)
    out: List[dict] = []
    for wagon, members in sorted(wagon_members.items()):
        if len(members) < min_size:
            continue
        is_sep, coh_d, max_coupling_d, neighbor = _separable(wagon, wagon_members, edges)
        if not is_sep:
            out.append({
                "source_node_or_scope": f"wagon:{wagon}",
                "relationship": "wmbt cohesion-density < neighbor coupling-density [MERGE]",
                "actual_count": round(coh_d, 3),
                "min": round(max_coupling_d, 3),
                "targets": [neighbor] if neighbor else [],
            })
    return out


# --- template dispatch ------------------------------------------------------
_VARIANTS = {
    "wagon_coupling_complexity": evaluate_coupling_complexity,
    "wagon_separability": evaluate_separability,
}


def _cardinality_bounds(graph, config=None) -> List[dict]:
    """Dispatch the `cardinality_bounds` template to its advisory sizing variant.

    ``config['variant']`` selects the metric; there is no default because the two
    variants measure different relationships (a silent default would hide which
    advisory ran).
    """
    config = config or {}
    variant = config.get("variant")
    fn = _VARIANTS.get(variant)
    if fn is None:
        raise ValueError(
            f"sizing/cardinality_bounds requires config['variant'] in {sorted(_VARIANTS)}; got {variant!r}"
        )
    return fn(graph, config)


REAL_EVALUATORS = {"cardinality_bounds": _cardinality_bounds}
