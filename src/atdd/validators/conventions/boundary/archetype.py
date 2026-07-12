"""Reusable graph-question archetype for the `boundary` family (#1204, #1206, #1212).

The `boundary/allowed_boundary_crossing` template asks: *does this edge, import,
or reference cross only allowed package/layer boundaries?* It is executed against
the REAL composed convention graph — wagon nodes carry ``.theme`` (the layer a
wagon belongs to) and ``.package`` / ``fields["wagon"]`` (the slug locating its
source tree on disk). The module-import graph that the boundary policy constrains
is read from the filesystem under ``graph.root`` (the same substrate the
resolution sentinels use for on-disk artifact refs).

Variant ``theme_commons_coach_boundary`` (legacy
``planner.theme.commons-coach-boundary``): a wagon is ``commons`` IFF a non-coach
archetype can consume its artifacts WITHOUT importing ``atdd.coach``. Concretely,
no module under a ``commons``-themed wagon's source tree may import ``atdd.coach``.

This module is self-contained (it imports NO persona validator module) so the
convention family runs in parallel with — and ultimately decommissions — the
legacy validators (#1212).
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .._support.template_contract import TemplateContract

_log = logging.getLogger(__name__)

TEMPLATES = [
    TemplateContract(
        family_id='boundary',
        template_id='allowed_boundary_crossing',
        question='Does this edge, import, or reference cross only allowed package/layer boundaries?',
        selector='edges/imports/references with source and target ownership metadata',
        traversal='source node/package -> edge/import/ref -> target node/package -> boundary policy',
        invariant='boundary_policy.allows(source, target, edge_type)',
        auto_capture='a new node is included if it declares ownership/package/layer metadata and participates in edges',
        failure_evidence=['source', 'target', 'edge_type', 'source_boundary', 'target_boundary', 'violated_policy'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]

# ---------------------------------------------------------------------------
# Deferred wagons — themed ``commons`` but legitimately importing coach until
# the #951 recompose re-themes them. MIRRORS the legacy single-source set
# (planner.validators._theme_taxonomy.DEFERRED_RETHEME_WAGONS); not imported, to
# keep the convention family free of persona-validator imports (parallel-safe,
# #1212). Delete entries here as #951 re-themes each wagon — same as legacy.
# ---------------------------------------------------------------------------
DEFERRED_RETHEME_WAGONS: frozenset = frozenset(
    {"mediate-worker-decisions", "consolidate-coach-workspace"}
)


def _module_imports(py_path: Path, forbidden_prefix: str) -> bool:
    """True iff *py_path* imports the ``forbidden_prefix`` package (AST-accurate).

    Mirrors the legacy AST detector: matches ``import <pkg>`` / ``import <pkg>.x``,
    ``from <pkg>[.x] import ...`` and ``from <parent> import <leaf>`` forms.
    """
    parent, _, leaf = forbidden_prefix.rpartition(".")
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError) as exc:
        # Unparseable module: skip (never silently swallow). Same posture as the
        # legacy scan — a syntax error here is not an import-boundary violation.
        _log.info("boundary scan skipped unparseable module",
                  extra={"path": str(py_path), "error": repr(exc)[:120]})
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == forbidden_prefix or a.name.startswith(forbidden_prefix + ".")
                   for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == forbidden_prefix or mod.startswith(forbidden_prefix + "."):
                return True
            if parent and mod == parent and any(a.name == leaf for a in node.names):
                return True
    return False


# Default config for the only landed variant. ``TemplateContract.evaluate`` passes
# this through to the evaluator; tests select a variant by passing its config.
VARIANT_CONFIGS: Dict[str, dict] = {
    "theme_commons_coach_boundary": {
        "variant": "theme_commons_coach_boundary",
        "source_theme": "commons",          # the layer that owns the boundary
        "target_boundary": "coach",         # the layer it may not cross into
        "forbidden_import": "atdd.coach",   # concrete import that crosses it
        "violated_policy": "planner.theme.commons-coach-boundary",
        "deferred_wagons": sorted(DEFERRED_RETHEME_WAGONS),
    },
}

_DEFAULT_VARIANT = "theme_commons_coach_boundary"


def evaluate_allowed_boundary_crossing(graph, config: Optional[dict] = None) -> List[dict]:
    """Execute ``allowed_boundary_crossing`` over the REAL composed graph.

    selector  : wagon nodes whose ``.theme`` == config['source_theme'] (auto-capture
                — any wagon declaring that theme + a locatable source tree).
    traversal : wagon -> modules under src/atdd/<slug> -> import edges -> target pkg.
    invariant : no selected wagon's module may import config['forbidden_import'].
    evidence  : subset of the template's failure_evidence.

    ``config`` selects the variant; deferred wagons (themed source_theme but
    legitimately crossing, pending #951) are excluded — matching legacy.
    """
    cfg = dict(VARIANT_CONFIGS[_DEFAULT_VARIANT])
    if config:
        cfg.update(config)

    source_theme = cfg["source_theme"]
    forbidden = cfg["forbidden_import"]
    target_boundary = cfg["target_boundary"]
    policy = cfg["violated_policy"]
    deferred = set(cfg.get("deferred_wagons") or ())

    root = getattr(graph, "root", None)
    if root is None:
        # The boundary policy constrains the on-disk module-import graph; without a
        # filesystem root there are no import edges to traverse.
        return []
    root = Path(root)

    out: List[dict] = []
    for wagon in graph.by_kind("wagon"):
        if wagon.theme != source_theme:
            continue
        slug = wagon.fields.get("wagon") or wagon.package
        if slug in deferred:
            continue
        src = root / "src" / "atdd" / str(slug).replace("-", "_")
        if not src.is_dir():
            continue
        for py in sorted(src.rglob("*.py")):
            if _module_imports(py, forbidden):
                out.append({
                    "source": f"{slug}:{py.relative_to(root).as_posix()}",
                    "target": forbidden,
                    "edge_type": "import",
                    "source_boundary": source_theme,
                    "target_boundary": target_boundary,
                    "violated_policy": policy,
                })
                break  # one violation per wagon (matches legacy's per-wagon break)
    return out


# Auto-discovered by _support.evaluators (do NOT edit that shared map). Keyed by
# template_id; the real composed graph is the only substrate.
REAL_EVALUATORS = {
    "allowed_boundary_crossing": evaluate_allowed_boundary_crossing,
}
