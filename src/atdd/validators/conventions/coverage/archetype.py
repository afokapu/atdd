"""Reusable graph-question archetype for the `coverage` family (#1204).

Real-graph execution (#1212): each template's selector -> traversal -> invariant
runs over real ``graph_loader.Node`` objects (the composed convention graph), not
dict fixtures. ``REAL_EVALUATORS`` exposes the family's evaluators template-keyed
so ``_support.evaluators`` auto-discovers them without editing the shared map.

Two templates, three variants:
  - source_has_required_target  -> hierarchy_coverage | wmbt_has_smoke_acceptance
  - reachability_no_orphan      -> no_orphan_nodes

``config`` selects the variant for the shared ``source_has_required_target``
template (``config={"variant": ...}``).
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional

import yaml

from .._support.template_contract import TemplateContract

_log = logging.getLogger(__name__)

TEMPLATES = [
    TemplateContract(
        family_id='coverage',
        template_id='reachability_no_orphan',
        question='Is every required node reachable from a valid root or owner?',
        selector='nodes where requires_reachability != false',
        traversal='root nodes -> allowed edges -> reachable set',
        invariant='eligible node is in reachable set',
        auto_capture='a new node is included if its kind/package requires reachability by default',
        failure_evidence=['orphan_node', 'expected_root', 'allowed_paths', 'node_location'],
    ),
    TemplateContract(
        family_id='coverage',
        template_id='source_has_required_target',
        question='For every source node of type X, does required downstream target Y exist?',
        selector='nodes where node.coverage.requires exists',
        traversal='source node -> required relationship/path -> target node set',
        invariant='target set is non-empty and satisfies required target kind/filter',
        auto_capture='a new node is included if it declares coverage requirements',
        failure_evidence=['source_node', 'required_target_kind', 'required_path', 'actual_targets'],
    ),
    # train-interlocking projection coverage (#1249 / parent #1246). Asks: does
    # every element of a SOURCE space (executable guard paths; WMBT obligations)
    # project onto a target (a train route; a surface/residual)? Each source item
    # must be covered exactly once or be an explicit structural residual.
    TemplateContract(
        family_id='coverage',
        template_id='projection_covers_source',
        question='Does every element of the source space project onto exactly one covered target (or an explicit residual)?',
        selector='subjects declaring a source space that must project onto a target space (e.g. interlocking guards/WMBTs)',
        traversal='subject -> source items -> projection -> covered target | structural residual',
        invariant='every source item is covered once or explicitly classified as a structural residual',
        auto_capture='a subject is included only when it declares a projection this template knows',
        failure_evidence=['interlocking_id', 'guard_id', 'route_id', 'coverage_status',
                          'wmbt_ref', 'surface_kind', 'residual_id'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]


# ---------------------------------------------------------------------------
# variant: hierarchy_coverage  (template source_has_required_target)
#
# Bidirectional hierarchy coverage over the composed graph:
#   train  -> wagon       every wagon is a participant of >=1 train
#   wagon  -> feature     every wagon references >=1 (resolving) feature
#   feature-> wmbt        every feature references >=1 (resolving) wmbt
#   wmbt   -> acceptance  every wmbt declares >=1 acceptance
#
# The fully-reverse legs (feature-referenced-by-wagon, wmbt-referenced-by-feature)
# are intentionally EXCLUDED: on the real repo 2 features and 27 wmbts are not
# back-referenced, and legacy COVERAGE-PLAN-2.2a/2.3 emit those only as warnings
# (phase-gated, never fail). Including them would create clean-repo false
# positives, so they are out of scope here (honest parity over warn-only legs).
# ---------------------------------------------------------------------------
def _hierarchy_coverage(graph) -> List[dict]:
    out: List[dict] = []
    ids = graph.ids()
    wagons = graph.by_kind('wagon')
    feats = graph.by_kind('feature')
    wmbts = graph.by_kind('wmbt')
    trains = graph.by_kind('train')

    train_wagon_refs = {r for t in trains for r in graph.refs_from(t)}
    for w in wagons:
        if w.id not in train_wagon_refs:
            out.append({'source_node': w.id, 'required_target_kind': 'train',
                        'required_path': w.location, 'actual_targets': []})
    for w in wagons:
        resolving = [r for r in graph.refs_from(w) if r in ids]
        if not resolving:
            out.append({'source_node': w.id, 'required_target_kind': 'feature',
                        'required_path': w.location, 'actual_targets': list(w.refs)})
    for f in feats:
        resolving = [r for r in graph.refs_from(f) if r in ids]
        if not resolving:
            out.append({'source_node': f.id, 'required_target_kind': 'wmbt',
                        'required_path': f.location, 'actual_targets': list(f.refs)})
    for m in wmbts:
        accs = m.fields.get('acceptances') or []
        if not accs:
            out.append({'source_node': m.id, 'required_target_kind': 'acceptance',
                        'required_path': m.location, 'actual_targets': []})
    return out


# ---------------------------------------------------------------------------
# variant: wmbt_has_smoke_acceptance  (template source_has_required_target)
#
# Every WMBT must declare >=1 acceptance whose urn carries the SMOKE harness
# token. Inline-suppressed WMBTs (legacy disposition `suppress-and-clean`) are
# skipped so the clean repo stays at 0 — mirroring legacy's disposition gate.
# ---------------------------------------------------------------------------
_SMOKE_URN_RE = re.compile(
    r"^acc:[a-z][a-z0-9-]*:[DLPCEMYRK]\d{3}-SMOKE-\d{3}(?:-[a-z0-9-]+)?$"
)
_SMOKE_SUPPRESS_RULE = 'planner.wmbt.must-have-smoke-acceptance'


def _acceptance_urns(fields: dict) -> List[str]:
    urns: List[str] = []
    for acc in fields.get('acceptances', []) or []:
        if isinstance(acc, dict):
            urn = (acc.get('identity') or {}).get('urn')
            if isinstance(urn, str) and urn:
                urns.append(urn)
        elif isinstance(acc, str) and acc:
            urns.append(acc)
    return urns


def _inline_suppressed(graph, node, rule_id: str) -> bool:
    """True when the node's source file carries an inline suppression marker for
    ``rule_id`` (mirrors the legacy disposition gate's marker scan)."""
    if graph.root is None:
        return False
    try:
        txt = (graph.root / node.location).read_text(encoding='utf-8')
    except OSError as exc:
        _log.info("suppression scan skipped (unreadable source)",
                  extra={"node": node.id, "location": node.location, "error": str(exc)[:120]})
        return False
    return f'atdd:suppress({rule_id})' in txt


def _wmbt_has_smoke_acceptance(graph) -> List[dict]:
    out: List[dict] = []
    for m in graph.by_kind('wmbt'):
        urns = _acceptance_urns(m.fields)
        if any(_SMOKE_URN_RE.match(u) for u in urns):
            continue
        if _inline_suppressed(graph, m, _SMOKE_SUPPRESS_RULE):
            continue
        out.append({'source_node': m.id, 'required_target_kind': 'acceptance:SMOKE',
                    'required_path': m.location, 'actual_targets': urns})
    return out


# ---------------------------------------------------------------------------
# variant: no_orphan_nodes  (template reachability_no_orphan)
#
# Every rule-bearing convention node (a *.convention.yaml with a top-level
# `rule_id`, fixtures + the demo.* namespace excluded) must be reachable as a
# source_ref/target_ref endpoint of the relationship graph
# (src/atdd/coach/graph/relationships.yaml). A node referenced by no edge is an
# orphan. Reads the same two real sources legacy reads, via ``graph.root``.
# ---------------------------------------------------------------------------
def _convention_rule_nodes(conv_root) -> dict:
    nodes: dict = {}
    for f in conv_root.rglob('*.convention.yaml'):
        s = str(f)
        if 'tests/fixtures' in s or '/fixtures/' in s:
            continue
        try:
            d = yaml.safe_load(f.read_text(encoding='utf-8')) or {}
        except yaml.YAMLError as exc:
            _log.info("no_orphan skipped unparseable convention",
                      extra={"path": s, "error": str(exc).splitlines()[0][:120]})
            continue
        rid = d.get('rule_id')
        if rid and not str(rid).startswith('demo.'):
            nodes[str(rid)] = f
    return nodes


def _relationship_endpoints(graph_path) -> set:
    refs: set = set()
    if not graph_path.exists():
        return refs
    try:
        gd = yaml.safe_load(graph_path.read_text(encoding='utf-8')) or {}
    except yaml.YAMLError as exc:
        _log.info("no_orphan skipped unparseable relationship graph",
                  extra={"path": str(graph_path), "error": str(exc).splitlines()[0][:120]})
        return refs
    for edge in gd.get('edges', []) or []:
        for key in ('source_ref', 'target_ref'):
            val = edge.get(key)
            if val:
                refs.add(str(val).split('#', 1)[0])
    return refs


def _no_orphan_nodes(graph) -> List[dict]:
    if graph.root is None:
        return []
    root = graph.root
    nodes = _convention_rule_nodes(root / 'src' / 'atdd')
    referenced = _relationship_endpoints(
        root / 'src' / 'atdd' / 'coach' / 'graph' / 'relationships.yaml')
    out: List[dict] = []
    for rid, path in sorted(nodes.items()):
        if rid not in referenced:
            out.append({'orphan_node': rid,
                        'expected_root': 'relationship-graph edge endpoint',
                        'allowed_paths': ['source_ref', 'target_ref'],
                        'node_location': str(path.relative_to(root))})
    return out


# ---------------------------------------------------------------------------
# template-keyed dispatch (config selects the variant for the shared template)
# ---------------------------------------------------------------------------
_SOURCE_VARIANTS = {
    'hierarchy_coverage': _hierarchy_coverage,
    'wmbt_has_smoke_acceptance': _wmbt_has_smoke_acceptance,
}


def _source_has_required_target(graph, config: Optional[dict] = None) -> List[dict]:
    variant = (config or {}).get('variant', 'hierarchy_coverage')
    fn = _SOURCE_VARIANTS.get(variant)
    if fn is None:
        raise ValueError(
            f"unknown coverage source_has_required_target variant {variant!r}; "
            f"expected one of {sorted(_SOURCE_VARIANTS)}"
        )
    return fn(graph)


def _reachability_no_orphan(graph, config: Optional[dict] = None) -> List[dict]:
    return _no_orphan_nodes(graph)


# ---------------------------------------------------------------------------
# template: projection_covers_source  (#1249 / parent #1246)
#
# Two interlocking variants over the canonical-home artifacts:
#   planner_train_interlocking_guard_coverage       -> every executable guard
#       path maps to exactly one route, unless declared a structural residual.
#   planner_train_interlocking_wmbt_surface_or_residual -> every WMBT obligation
#       (an invariant's wmbt_ref) surfaces or is an explicit structural residual.
# Both auto-capture: they fire only when a repo declares interlockings, so the
# clean repo (no interlockings) stays at 0.
# ---------------------------------------------------------------------------
def _interlocking_guard_coverage(graph) -> List[dict]:
    from atdd.planner.interlocking import InterlockingError, load_interlocking
    from atdd.planner.interlocking.discovery import iter_interlocking_paths

    root = graph.root
    if root is None:
        return []
    out: List[dict] = []
    for path in iter_interlocking_paths(root):
        try:
            il = load_interlocking(path)
        except InterlockingError:
            continue  # shape failures are owned by the schema family, not coverage
        routed_guards = {r.guard_ref: r.route_id for r in il.routes}
        residual_guards = {
            rsd.id for rsd in il.residuals if rsd.kind == "structural"
        }
        for guard_id in il.guard_index():
            if guard_id in routed_guards:
                continue
            if guard_id in residual_guards:
                continue
            out.append({"interlocking_id": il.interlocking_id, "guard_id": guard_id,
                        "route_id": None, "coverage_status": "uncovered"})
    return out


def _interlocking_wmbt_surface_or_residual(graph) -> List[dict]:
    from atdd.planner.interlocking import InterlockingError, load_interlocking
    from atdd.planner.interlocking.discovery import iter_interlocking_paths

    root = graph.root
    if root is None:
        return []
    out: List[dict] = []
    for path in iter_interlocking_paths(root):
        try:
            il = load_interlocking(path)
        except InterlockingError:
            continue
        surfaced = {inv.wmbt_ref for inv in il.invariants if inv.wmbt_ref}
        for msg in il.messages:
            surfaced.update(msg.feature_refs)
        residual_wmbts = {
            rsd.id for rsd in il.residuals if rsd.kind == "structural"
        }
        # An obligation is unsurfaced only when an invariant names a wmbt_ref that
        # is never carried by another surface and is not a declared residual.
        for inv in il.invariants:
            ref = inv.wmbt_ref
            if not ref:
                continue
            if ref in surfaced:
                continue
            if ref in residual_wmbts:
                continue
            out.append({"interlocking_id": il.interlocking_id, "wmbt_ref": ref,
                        "surface_kind": "invariant", "residual_id": None,
                        "coverage_status": "unsurfaced"})
    return out


_PROJECTION_VARIANTS = {
    'planner_train_interlocking_guard_coverage': _interlocking_guard_coverage,
    'planner_train_interlocking_wmbt_surface_or_residual': _interlocking_wmbt_surface_or_residual,
}


def _projection_covers_source(graph, config: Optional[dict] = None) -> List[dict]:
    variant = (config or {}).get('variant')
    fn = _PROJECTION_VARIANTS.get(variant)
    if fn is None:
        raise ValueError(
            f"unknown coverage projection_covers_source variant {variant!r}; "
            f"expected one of {sorted(_PROJECTION_VARIANTS)}"
        )
    return fn(graph)


REAL_EVALUATORS = {
    'source_has_required_target': _source_has_required_target,
    'reachability_no_orphan': _reachability_no_orphan,
    'projection_covers_source': _projection_covers_source,
}
