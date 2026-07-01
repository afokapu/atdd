"""Reusable graph-question archetype for the `coherence` family (#1204 / #1212).

Template ``resolved_fact_agreement`` asks: after a node's references resolve, do
the two facts you derive from that node agree under a declared predicate? Each
variant pins a concrete fact-pair + predicate and runs over the REAL composed
convention graph (``_support.graph_loader.ConventionGraph`` of ``Node`` objects).

Evidence dicts use keys ⊆ ['source_node','fact_a','fact_b','predicate','actual_values'].
"""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import List

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='coherence',
        template_id='resolved_fact_agreement',
        question='After references resolve, do the resolved facts agree with each other?',
        selector='nodes declaring coherence checks or semantic comparison rules',
        traversal='source node -> resolved fact A; source node -> resolved fact B; compare A and B',
        invariant='facts satisfy comparison predicate',
        auto_capture='partial; a new node is included only if it declares a known coherence predicate',
        failure_evidence=['source_node', 'fact_a', 'fact_b', 'predicate', 'actual_values'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]

# theme -> archetype source-root segment under src/atdd/ (legacy _ARCHETYPE_FOR_THEME).
_ARCHETYPE_FOR_THEME = {"plan": "planner", "test": "tester", "code": "coder"}

# Wagons whose theme/URN re-namespacing is deferred to the #951 recompose co-land
# (legacy _theme_taxonomy.DEFERRED_RETHEME_WAGONS). The convention evaluator mirrors
# legacy's production filter so the divergence set matches the legacy check exactly.
_DEFERRED_RETHEME_WAGONS = frozenset({
    "mediate-worker-decisions",
    "consolidate-coach-workspace",
})

_COMMIT_RECEIPT = "platform:acceptance:commit-receipt"
_VALID_TRAIN_FAMILIES = ("behavior", "delivery")


def _wagon_slug(node) -> str:
    return node.fields.get("wagon") or node.package or node.id


# --- variant: theme_urn_namespace_matches ----------------------------------
def _theme_urn_namespace_matches(graph) -> List[dict]:
    """Produced contract/telemetry URN theme-prefix MUST equal the wagon's
    declared ``theme:`` (legacy planner.theme.urn-namespace-matches)."""
    out: List[dict] = []
    for w in graph.by_kind("wagon"):
        theme = w.theme
        for produced in (w.fields.get("produce") or []):
            if not isinstance(produced, dict):
                continue
            name = produced.get("name") or ""
            if ":" not in name:
                continue
            prefix = name.split(":", 1)[0]
            if prefix != theme:
                out.append({
                    "source_node": w.id,
                    "fact_a": theme,
                    "fact_b": prefix,
                    "predicate": "produced-urn-theme-prefix == wagon-theme",
                    "actual_values": {"wagon_theme": theme, "produced_urn": name,
                                      "urn_prefix": prefix},
                })
    return out


# --- variant: theme_archetype_alignment ------------------------------------
def _theme_archetype_alignment(graph) -> List[dict]:
    """A wagon themed plan/test/code MUST have its implementation under the
    matching planner/tester/coder source root (legacy
    planner.theme.archetype-alignment)."""
    out: List[dict] = []
    root = graph.root
    if root is None:
        return out
    src_root = root / "src" / "atdd"
    if not src_root.is_dir():
        return out
    for w in graph.by_kind("wagon"):
        theme = w.theme
        expected = _ARCHETYPE_FOR_THEME.get(theme)
        if expected is None:
            continue  # commons / coach have no archetype-root constraint
        under = _wagon_slug(w).replace("-", "_")
        found = [p for p in src_root.rglob(under) if p.is_dir()]
        if not found:
            continue  # documentation-only: source not locatable by slug
        for p in found:
            parts = p.relative_to(src_root).parts
            if expected not in parts:
                out.append({
                    "source_node": w.id,
                    "fact_a": f"src/atdd/{expected}",
                    "fact_b": str(p.relative_to(root)),
                    "predicate": "wagon-source-root contains archetype-for-theme",
                    "actual_values": {"theme": theme, "expected_root": expected,
                                      "actual_source": str(p.relative_to(root))},
                })
    return out


# --- variant: train_family_matches_terminal_contract -----------------------
def _train_family_matches_terminal_contract(graph) -> List[dict]:
    """A train's declared ``family`` MUST agree with its terminal step artifact:
    commit-receipt terminal <=> family 'delivery' (legacy
    planner.train.family-matches-terminal-contract). A train with no ``family``
    is not flagged (optional during the #1083 transition)."""
    out: List[dict] = []
    for t in graph.by_kind("train"):
        family = t.fields.get("family")
        if family is None:
            continue
        sequence = t.fields.get("sequence") or []
        terminal = sequence[-1].get("artifact") if sequence else None
        terminal_is_receipt = terminal == _COMMIT_RECEIPT
        bad = (
            family not in _VALID_TRAIN_FAMILIES
            or (terminal_is_receipt and family != "delivery")
            or (family == "delivery" and not terminal_is_receipt)
        )
        if bad:
            out.append({
                "source_node": t.id,
                "fact_a": family,
                "fact_b": terminal,
                "predicate": "family=='delivery' iff terminal artifact is commit-receipt",
                "actual_values": {"family": family, "terminal_artifact": terminal,
                                  "terminal_is_commit_receipt": terminal_is_receipt},
            })
    return out


# --- variant: wmbt_consistency ---------------------------------------------
def _wmbt_consistency(graph) -> List[dict]:
    """Declared WMBT references in a wagon manifest MUST agree (both directions)
    with the WMBT YAML files present in the wagon directory — the filesystem is
    the source of truth (legacy test_wmbt_consistency)."""
    from collections import defaultdict
    files: dict = defaultdict(set)            # package -> {CODE}
    for m in graph.by_kind("wmbt"):
        code = PurePosixPath(m.location).name.removesuffix(".yaml")
        files[m.package].add(code)

    out: List[dict] = []
    for w in graph.by_kind("wagon"):
        sec = w.fields.get("wmbt")
        if not sec:
            continue
        if isinstance(sec, dict):
            declared = {k for k in sec if k not in ("total", "coverage")}
        elif isinstance(sec, list):
            declared = {(i.get("id") if isinstance(i, dict) else i) for i in sec}
            declared.discard(None)
        else:
            continue
        actual = files.get(w.package, set())
        missing = declared - actual          # declared in manifest, no file
        undeclared = actual - declared        # file present, not declared
        if missing or undeclared:
            out.append({
                "source_node": w.id,
                "fact_a": sorted(declared),
                "fact_b": sorted(actual),
                "predicate": "manifest-declared WMBT codes == filesystem WMBT files",
                "actual_values": {"declared_only": sorted(missing),
                                  "files_only": sorted(undeclared)},
            })
    return out


# --- train-interlocking coherence variants (#1249 / parent #1246) ----------
# Each scans the canonical-home interlocking artifacts and asks whether two facts
# derived from a route agree. Auto-capture: they fire only when a repo declares
# interlockings, so the clean repo (none) stays at 0. Evidence keys are a SUBSET
# of the coherence template contract ['source_node','fact_a','fact_b','predicate',
# 'actual_values'].
def _iter_interlockings(graph):
    from atdd.planner.interlocking import InterlockingError, load_interlocking
    from atdd.planner.interlocking.discovery import iter_interlocking_paths

    root = graph.root
    if root is None:
        return
    for path in iter_interlocking_paths(root):
        try:
            yield load_interlocking(path)
        except InterlockingError:
            continue  # shape failures are owned by the schema family


def _interlocking_route_category_matches_train_id(graph) -> List[dict]:
    from atdd.planner.interlocking.models import CATEGORY_BY_DIGIT
    out: List[dict] = []
    for il in _iter_interlockings(graph):
        for route in il.routes:
            train_digit = route.train_id[1] if len(route.train_id) >= 2 else ""
            expected_cat = CATEGORY_BY_DIGIT.get(route.category_digit)
            if route.category_digit != train_digit or (
                expected_cat is not None and route.category != expected_cat
            ):
                out.append({
                    "source_node": f"{il.interlocking_id}:{route.route_id}",
                    "fact_a": route.category_digit,
                    "fact_b": train_digit,
                    "predicate": "route.category_digit == train_id category digit and category matches",
                    "actual_values": {"category": route.category,
                                      "train_id": route.train_id,
                                      "category_digit": route.category_digit,
                                      "train_digit": train_digit},
                })
    return out


def _interlocking_route_resolution_deterministic(graph) -> List[dict]:
    out: List[dict] = []
    allowed = {"fail_on_multiple_match", "first_priority"}
    for il in _iter_interlockings(graph):
        strategy = il.route_resolution.strategy
        priorities = [r.priority for r in il.routes]
        bad_strategy = strategy not in allowed
        non_unique = strategy == "first_priority" and len(set(priorities)) != len(priorities)
        if bad_strategy or non_unique:
            out.append({
                "source_node": il.interlocking_id,
                "fact_a": strategy,
                "fact_b": sorted(priorities),
                "predicate": "strategy is declared+deterministic; first_priority needs unique priorities",
                "actual_values": {"strategy": strategy, "priorities": priorities,
                                  "route_ids": [r.route_id for r in il.routes]},
            })
    return out


def _interlocking_projection_equivalence(graph) -> List[dict]:
    from atdd.planner.interlocking import InterlockingError
    from atdd.planner.interlocking.digest import route_projection_digest
    from atdd.planner.interlocking.projections import project_route_to_train_sequence
    out: List[dict] = []
    for il in _iter_interlockings(graph):
        for route in il.routes:
            try:
                steps = project_route_to_train_sequence(il, route.route_id)
            except InterlockingError as exc:
                out.append({
                    "source_node": f"{il.interlocking_id}:{route.route_id}",
                    "fact_a": route.projection.expected_sequence_digest,
                    "fact_b": None,
                    "predicate": "route projects onto its train's linear sequence",
                    "actual_values": {"train_id": route.train_id, "error": str(exc)[:160]},
                })
                continue
            computed = route_projection_digest(steps, route.projection.fields)
            if computed != route.projection.expected_sequence_digest:
                out.append({
                    "source_node": f"{il.interlocking_id}:{route.route_id}",
                    "fact_a": route.projection.expected_sequence_digest,
                    "fact_b": computed,
                    "predicate": "expected projection digest == computed train-sequence digest",
                    "actual_values": {"train_id": route.train_id,
                                      "expected": route.projection.expected_sequence_digest,
                                      "computed": computed},
                })
    return out


_VARIANTS = {
    "theme_urn_namespace_matches": _theme_urn_namespace_matches,
    "theme_archetype_alignment": _theme_archetype_alignment,
    "train_family_matches_terminal_contract": _train_family_matches_terminal_contract,
    "wmbt_consistency": _wmbt_consistency,
    "planner_train_interlocking_route_category_matches_train_id":
        _interlocking_route_category_matches_train_id,
    "planner_train_interlocking_route_resolution_deterministic":
        _interlocking_route_resolution_deterministic,
    "planner_train_interlocking_projection_equivalence":
        _interlocking_projection_equivalence,
}


def resolved_fact_agreement(graph, config=None) -> List[dict]:
    """Execute the ``resolved_fact_agreement`` template for the variant named in
    ``config={"variant": ...}`` over the real composed graph."""
    config = config or {}
    variant = config.get("variant")
    fn = _VARIANTS.get(variant)
    if fn is None:
        raise NotImplementedError(
            f"coherence/resolved_fact_agreement: unknown variant {variant!r}; "
            f"known variants: {sorted(_VARIANTS)}"
        )
    return fn(graph)


REAL_EVALUATORS = {"resolved_fact_agreement": resolved_fact_agreement}
