# Component: component:atdd-plan-core:validators:ComponentBlockReader:backend:domain
"""Shared reader for the ``components:`` block on plan feature files (#1639).

The three ``planner.component.*`` rules bound in #1639 all walk the same
structure, so the walk lives here once and each validator module states one
rule over it.

Shape actually authored in ``plan/<wagon>/features/<feature>.yaml``::

    components:
      backend:                      # side
        application:                # layer
          - type: use_cases         # component type
            count: 2
            rationale: "..."

Note this is NOT the ``component:{wagon}:{feature}:{name}:{side}:{layer}`` URN
shape in ``component.schema.json``. The corpus carries typed counts, not URNs;
#1639 measured 0 component URNs across 162 feature files, which is why
``planner.component.urn`` is deliberately left unbound rather than shipped as a
gate that is green only because its subject is empty.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Set, Tuple

import yaml

_log = logging.getLogger(__name__)

# Sentinel layer for entries authored without one (``{side: [items]}``). No
# catalog declares it, so every rule that judges layers reports it.
LAYER_ABSENT = ""

# The catalog node is the authority on which (side, layer, type) triples exist.
_CATALOG_NODE = (
    Path(__file__).resolve().parent.parent
    / "conventions" / "nodes"
    / "planner.component.type-catalog.convention.yaml"
)


@dataclass(frozen=True)
class ComponentEntry:
    """One ``{type, count}`` entry, with the feature file and keys it sat under."""

    feature: Path
    side: str
    layer: str
    type_name: str
    count: int


def load_catalog() -> Dict[str, Dict[str, Set[str]]]:
    """``{side: {layer: {type, ...}}}`` from the type-catalog node's terms.

    Returns ``{}`` when the node is unreadable, which the callers treat as
    "cannot judge" rather than "everything is a violation".
    """
    terms = _catalog_terms()
    sides = (("backend", "backend_catalog"), ("frontend", "frontend_catalog"))
    return {side: _side_catalog(terms.get(term_id)) for side, term_id in sides}


def _catalog_terms() -> Dict[str, object]:
    """``{term_id: values}`` from the catalog node, ``{}`` when unreadable."""
    try:
        doc = yaml.safe_load(_CATALOG_NODE.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        # Never silent: an unreadable catalog disables every catalog-judging
        # rule, so it must be visible rather than looking like a clean corpus.
        _log.warning(
            "component type-catalog node unreadable; catalog rules will judge nothing",
            extra={"path": str(_CATALOG_NODE), "error": str(exc).splitlines()[0][:160]},
        )
        return {}
    return {t.get("term_id"): (t.get("values") or {}) for t in (doc.get("terms") or [])}


def _side_catalog(layers: object) -> Dict[str, Set[str]]:
    """``{layer: {type, ...}}`` for one side's catalog term value."""
    if not isinstance(layers, dict):
        return {}
    return {layer: set(types) for layer, types in layers.items() if isinstance(types, dict)}


def iter_feature_files(plan_dir: Path) -> Iterator[Path]:
    yield from sorted(plan_dir.glob("*/features/*.yaml"))


def read_components(feature: Path) -> Tuple[List[ComponentEntry], int]:
    """``(entries, total_count)`` for one feature file.

    A file with no ``components:`` block yields ``([], 0)`` — absence is not a
    violation of any rule bound here.
    """
    try:
        doc = yaml.safe_load(feature.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        _log.info(
            "component reader skipped an unparseable feature file",
            extra={"path": str(feature), "error": str(exc).splitlines()[0][:160]},
        )
        return [], 0
    block = doc.get("components")
    if not isinstance(block, dict):
        return [], 0

    entries: List[ComponentEntry] = []
    for side, layers in block.items():
        for layer, items in _by_layer(layers):
            entries.extend(_entries(feature, str(side), str(layer), items))
    return entries, sum(e.count for e in entries)


def _by_layer(layers: object) -> List[Tuple[str, list]]:
    """``[(layer, items), ...]`` for one side, normalising both authored shapes.

    The dominant shape nests a layer — ``{side: {layer: [items]}}`` — but a
    handful of entries omit it: ``{side: [items]}``. The layerless shape is NOT
    dropped; a component with no layer is itself a layer-assignment problem, and
    skipping it here would make every component rule silently under-report. It
    is surfaced under ``LAYER_ABSENT``, which no catalog declares.
    """
    if isinstance(layers, dict):
        return [(str(k), v or []) for k, v in layers.items()]
    if isinstance(layers, list):
        return [(LAYER_ABSENT, layers)]
    return []


def _entries(feature: Path, side: str, layer: str, items: list) -> Iterator[ComponentEntry]:
    for item in items or []:
        if not isinstance(item, dict):
            continue
        count = item.get("count")
        yield ComponentEntry(
            feature=feature,
            side=side,
            layer=layer,
            type_name=str(item.get("type")),
            count=count if isinstance(count, int) else 0,
        )
