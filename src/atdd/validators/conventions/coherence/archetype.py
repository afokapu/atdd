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
    "consolidate-coach-workspace",
})

_COMMIT_RECEIPT = "platform:acceptance:commit-receipt"
_VALID_TRAIN_FAMILIES = ("behavior", "delivery")


def _wagon_slug(node) -> str:
    return node.fields.get("wagon") or node.package or node.id


# --- variant: theme_urn_namespace_matches ----------------------------------
def _urn_theme_violation(w, produced) -> "dict | None":
    """The evidence for one produced URN whose theme-prefix disagrees with the
    wagon's theme, or ``None`` when it agrees (or carries no theme prefix)."""
    if not isinstance(produced, dict):
        return None
    name = produced.get("name") or ""
    if ":" not in name:
        return None
    prefix = name.split(":", 1)[0]
    if prefix == w.theme:
        return None
    return {
        "source_node": w.id,
        "fact_a": w.theme,
        "fact_b": prefix,
        "predicate": "produced-urn-theme-prefix == wagon-theme",
        "actual_values": {
            "wagon_theme": w.theme,
            "produced_urn": name,
            "urn_prefix": prefix,
        },
    }


def _theme_urn_namespace_matches(graph) -> List[dict]:
    """Produced contract/telemetry URN theme-prefix MUST equal the wagon's
    declared ``theme:`` (legacy planner.theme.urn-namespace-matches)."""
    out: List[dict] = []
    for w in graph.by_kind("wagon"):
        for produced in (w.fields.get("produce") or []):
            violation = _urn_theme_violation(w, produced)
            if violation is not None:
                out.append(violation)
    return out


# --- variant: theme_archetype_alignment ------------------------------------
def _archetype_misplacement(w, p, src_root, root, expected) -> "dict | None":
    """The evidence for one located source dir that sits outside the archetype
    root its wagon's theme demands, or ``None`` when it sits inside."""
    parts = p.relative_to(src_root).parts
    if expected in parts:
        return None
    return {
        "source_node": w.id,
        "fact_a": f"src/atdd/{expected}",
        "fact_b": str(p.relative_to(root)),
        "predicate": "wagon-source-root contains archetype-for-theme",
        "actual_values": {
            "theme": w.theme,
            "expected_root": expected,
            "actual_source": str(p.relative_to(root)),
        },
    }


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
        expected = _ARCHETYPE_FOR_THEME.get(w.theme)
        if expected is None:
            continue  # commons / coach have no archetype-root constraint
        under = _wagon_slug(w).replace("-", "_")
        found = [p for p in src_root.rglob(under) if p.is_dir()]
        if not found:
            continue  # documentation-only: source not locatable by slug
        for p in found:
            violation = _archetype_misplacement(w, p, src_root, root, expected)
            if violation is not None:
                out.append(violation)
    return out


# --- variant: train_family_matches_terminal_contract -----------------------
def _train_family_violation(t) -> "dict | None":
    """The evidence for one train whose ``family`` disagrees with its terminal
    step artifact, or ``None`` when they agree (or no ``family`` is declared)."""
    family = t.fields.get("family")
    if family is None:
        return None
    sequence = t.fields.get("sequence") or []
    terminal = sequence[-1].get("artifact") if sequence else None
    terminal_is_receipt = terminal == _COMMIT_RECEIPT
    bad = (
        family not in _VALID_TRAIN_FAMILIES
        or (terminal_is_receipt and family != "delivery")
        or (family == "delivery" and not terminal_is_receipt)
    )
    if not bad:
        return None
    return {
        "source_node": t.id,
        "fact_a": family,
        "fact_b": terminal,
        "predicate": "family=='delivery' iff terminal artifact is commit-receipt",
        "actual_values": {
            "family": family,
            "terminal_artifact": terminal,
            "terminal_is_commit_receipt": terminal_is_receipt,
        },
    }


def _train_family_matches_terminal_contract(graph) -> List[dict]:
    """A train's declared ``family`` MUST agree with its terminal step artifact:
    commit-receipt terminal <=> family 'delivery' (legacy
    planner.train.family-matches-terminal-contract). A train with no ``family``
    is not flagged (optional during the #1083 transition)."""
    out: List[dict] = []
    for t in graph.by_kind("train"):
        violation = _train_family_violation(t)
        if violation is not None:
            out.append(violation)
    return out


# --- variant: wmbt_consistency ---------------------------------------------
def _declared_wmbt_codes(sec) -> "set | None":
    """The WMBT codes a wagon manifest declares, or ``None`` when the ``wmbt``
    section has no recognised shape (mapping of codes, or list of ids/dicts)."""
    if isinstance(sec, dict):
        return {k for k in sec if k not in ("total", "coverage")}
    if isinstance(sec, list):
        declared = {(i.get("id") if isinstance(i, dict) else i) for i in sec}
        declared.discard(None)
        return declared
    return None


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
        declared = _declared_wmbt_codes(sec)
        if declared is None:
            continue
        actual = files.get(w.package, set())
        missing = declared - actual          # declared in manifest, no file
        undeclared = actual - declared        # file present, not declared
        if not (missing or undeclared):
            continue
        out.append({
            "source_node": w.id,
            "fact_a": sorted(declared),
            "fact_b": sorted(actual),
            "predicate": "manifest-declared WMBT codes == filesystem WMBT files",
            "actual_values": {
                "declared_only": sorted(missing),
                "files_only": sorted(undeclared),
            },
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


def _route_category_violation(il, route, root) -> "dict | None":
    """The evidence for one route whose ``category`` disagrees with its target
    train's ``category`` field, or ``None`` when they agree (or the train
    declares no category)."""
    from atdd.planner.interlocking import target_train_category

    train_category = target_train_category(route.train_path, root)
    if train_category is None or route.category == train_category:
        return None
    return {
        "source_node": f"{il.interlocking_id}:{route.route_id}",
        "fact_a": route.category,
        "fact_b": train_category,
        "predicate": "route.category == target train's category field",
        "actual_values": {
            "category": route.category,
            "train_id": route.train_id,
            "train_path": route.train_path,
            "train_category": train_category,
        },
    }


def _interlocking_route_category_matches_train_id(graph) -> List[dict]:
    """A route's ``category`` must agree with the ``category`` FIELD of the train
    it selects (#1421). A field compare — the identity carries no classification
    digit to parse. A train declaring no category is not judged (#1440)."""
    out: List[dict] = []
    for il in _iter_interlockings(graph):
        for route in il.routes:
            violation = _route_category_violation(il, route, graph.root)
            if violation is not None:
                out.append(violation)
    return out


def _interlocking_route_resolution_deterministic(graph) -> List[dict]:
    out: List[dict] = []
    allowed = {"fail_on_multiple_match", "first_priority"}
    for il in _iter_interlockings(graph):
        strategy = il.route_resolution.strategy
        priorities = [r.priority for r in il.routes]
        bad_strategy = strategy not in allowed
        non_unique = strategy == "first_priority" and len(set(priorities)) != len(priorities)
        if not (bad_strategy or non_unique):
            continue
        out.append({
            "source_node": il.interlocking_id,
            "fact_a": strategy,
            "fact_b": sorted(priorities),
            "predicate": "strategy is declared+deterministic; first_priority needs unique priorities",
            "actual_values": {
                "strategy": strategy,
                "priorities": priorities,
                "route_ids": [r.route_id for r in il.routes],
            },
        })
    return out


def _route_projection_violation(il, route) -> "dict | None":
    """The evidence for one route that fails to project onto its train's linear
    sequence, or whose computed digest differs from the declared one; ``None``
    when the projection reproduces the expected digest."""
    from atdd.planner.interlocking import InterlockingError
    from atdd.planner.interlocking.digest import route_projection_digest
    from atdd.planner.interlocking.projections import project_route_to_train_sequence

    source_node = f"{il.interlocking_id}:{route.route_id}"
    expected = route.projection.expected_sequence_digest
    failure = None
    try:
        steps = project_route_to_train_sequence(il, route.route_id)
    except InterlockingError as exc:
        # Surfaced as evidence below, never swallowed — the handler records the
        # reason rather than returning, so it stays out of the silent-swallow set.
        failure = str(exc)[:160]
    if failure is not None:
        return {
            "source_node": source_node,
            "fact_a": expected,
            "fact_b": None,
            "predicate": "route projects onto its train's linear sequence",
            "actual_values": {"train_id": route.train_id, "error": failure},
        }
    computed = route_projection_digest(steps, route.projection.fields)
    if computed == expected:
        return None
    return {
        "source_node": source_node,
        "fact_a": expected,
        "fact_b": computed,
        "predicate": "expected projection digest == computed train-sequence digest",
        "actual_values": {
            "train_id": route.train_id,
            "expected": expected,
            "computed": computed,
        },
    }


def _interlocking_projection_equivalence(graph) -> List[dict]:
    out: List[dict] = []
    for il in _iter_interlockings(graph):
        for route in il.routes:
            violation = _route_projection_violation(il, route)
            if violation is not None:
                out.append(violation)
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
