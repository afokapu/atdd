# URN: test:validate-conventions:boundary-variants:theme_commons_coach_boundary
# Acceptance: acc:govern-lifecycle:C003-UNIT-001-commons-wagon-importing-coach-is-flagged
# Acceptance: acc:govern-lifecycle:C003-SMOKE-001-plan-tree-respects-boundary
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `boundary/theme_commons_coach_boundary` (#1206, #1212).

Instantiates the `boundary/allowed_boundary_crossing` template against the REAL
composed convention graph. Traversal execution runs over genuine `Node` objects;
the boundary policy it enforces (no `commons`-themed wagon's source tree may
import `atdd.coach`) is the canonical form of legacy
`planner.theme.commons-coach-boundary`.

Runs in parallel with the legacy validator: this module imports NO persona
validator module (the legacy parity check shells out via subprocess).
"""
from __future__ import annotations

from pathlib import Path

from atdd.validators.conventions._support.graph_mutations import (
    graph_rooted_at,
    stage_file,
)
from atdd.validators.conventions.boundary import fixtures
from atdd.validators.conventions.boundary.archetype import (
    DEFERRED_RETHEME_WAGONS,
    TEMPLATE_IDS,
    TEMPLATES,
    VARIANT_CONFIGS,
)

FAMILY = "boundary"
TEMPLATE = "allowed_boundary_crossing"
VARIANT = "theme_commons_coach_boundary"
QUESTION = 'Does this edge, import, or reference cross only allowed package/layer boundaries?'
SELECTOR = 'edges/imports/references with source and target ownership metadata'
TRAVERSAL = 'source node/package -> edge/import/ref -> target node/package -> boundary policy'
INVARIANT = 'boundary_policy.allows(source, target, edge_type)'
AUTO_CAPTURE = 'a new node is included if it declares ownership/package/layer metadata and participates in edges'
FAILURE_EVIDENCE = ['source', 'target', 'edge_type', 'source_boundary', 'target_boundary', 'violated_policy']
LEGACY_PARITY_SOURCES = ['src/atdd/planner/validators/test_theme_commons_coach_boundary.py']

_TEMPLATE = next(t for t in TEMPLATES if t.template_id == TEMPLATE)
_CONFIG = VARIANT_CONFIGS[VARIANT]


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for cand in p.parents:
        if (cand / "pyproject.toml").is_file() and (cand / "src" / "atdd").is_dir():
            return cand
    raise RuntimeError("repo root not found")


def _evaluate(graph) -> list:
    return _TEMPLATE.evaluate(graph, _CONFIG)


# --- contract --------------------------------------------------------------
def test_theme_commons_coach_boundary_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in boundary archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_evidence_keys_subset_of_contract() -> None:
    """Every evidence dict's keys are a SUBSET of the template failure_evidence."""
    declared = set(_TEMPLATE.failure_evidence)
    root = _repo_root()
    with fixtures.fixtures_tmp() as tmp:
        graph = fixtures.build_graph(tmp, fixtures.INVALID_FRAGMENTS["commons_wagon_imports_coach"])
        viols = _evaluate(graph)
    assert viols, "invalid fragment must yield a violation"
    for v in viols:
        assert set(v) <= declared, f"evidence keys {set(v)} escape contract {declared}"
    assert declared == set(FAILURE_EVIDENCE)
    assert root.is_dir()


# --- fixtures (real ConventionGraph fragments) -----------------------------


def test_valid_fragment_commons_no_coach_import_clean() -> None:
    with fixtures.fixtures_tmp() as tmp:
        graph = fixtures.build_graph(tmp, fixtures.VALID_FRAGMENTS["commons_wagon_no_coach_import"])
        assert _evaluate(graph) == []


def test_valid_fragment_coach_wagon_may_import_coach() -> None:
    with fixtures.fixtures_tmp() as tmp:
        graph = fixtures.build_graph(tmp, fixtures.VALID_FRAGMENTS["coach_wagon_imports_coach"])
        assert _evaluate(graph) == []


def test_invalid_fragment_commons_imports_coach_caught() -> None:
    with fixtures.fixtures_tmp() as tmp:
        graph = fixtures.build_graph(tmp, fixtures.INVALID_FRAGMENTS["commons_wagon_imports_coach"])
        viols = _evaluate(graph)
    assert len(viols) == 1
    v = viols[0]
    assert v["target"] == "atdd.coach"
    assert v["edge_type"] == "import"
    assert v["source_boundary"] == "commons"
    assert v["target_boundary"] == "coach"
    assert v["source"].startswith("do-thing:")


def test_deferred_wagon_not_flagged() -> None:
    """A commons wagon importing coach but on the deferred list is excluded
    (parity with legacy drop_deferred)."""
    deferred_slug = sorted(DEFERRED_RETHEME_WAGONS)[0]
    with fixtures.fixtures_tmp() as tmp:
        graph = fixtures.build_graph(
            tmp, {"wagon": deferred_slug, "theme": "commons", "imports_coach": True}
        )
        assert _evaluate(graph) == []


# --- clean baseline on the REAL composed graph -----------------------------
def test_clean_baseline_real_graph_is_empty(clean_convention_graph) -> None:
    assert _evaluate(clean_convention_graph) == [], (
        "clean repo must yield zero boundary crossings (deferred wagons excluded)"
    )


# --- fault injection + legacy parity (BOTH must catch) ---------------------


def test_fault_injection_convention_catches(clean_convention_graph, tmp_path) -> None:
    """Stage a coach import under a real non-deferred commons wagon's source path in a
    temp root; assert the convention evaluator catches it and the real src/ tree is
    never written. Oracle retired (#1365).

    The evaluator selects wagons from the graph's NODES but reads the crossing out of
    the wagon's `.py` source via ast.parse, so the fault must be a real module it really
    parses — no node carries it. It does not have to live in the REAL src/ tree
    (#1458, E035). The wagon nodes come from the session graph and the import is staged
    under `tmp_path` at the wagon's own source path; every other wagon's src dir is
    absent from the temp root, which the evaluator already skips (`if not src.is_dir()`),
    so the target is the only wagon in scope — the same isolation the old test bought by
    picking a slug with no existing src dir.

    `boundary/_parity.py` is deleted with this change. It justified writing the real tree
    on the grounds that "the legacy validator imports/scans it — tmp_path is not an
    option"; that oracle was retired in #1365, so the constraint it encoded is gone.
    """
    root = Path(clean_convention_graph.root)

    # A real commons, non-deferred wagon whose src/atdd/<slug> dir does NOT exist, so
    # staging its source path in the temp root cannot collide with a real module.
    target_slug = None
    for w in clean_convention_graph.by_kind("wagon"):
        if w.theme != "commons":
            continue
        slug = w.fields.get("wagon") or w.package
        if slug in DEFERRED_RETHEME_WAGONS:
            continue
        if not (root / "src" / "atdd" / str(slug).replace("-", "_")).exists():
            target_slug = slug
            break
    assert target_slug, "no clean commons wagon available for fault injection"

    # Pre-condition: the real tree crosses no boundary.
    assert _evaluate(clean_convention_graph) == []

    pkg = str(target_slug).replace("-", "_")
    stage_file(
        tmp_path, f"src/atdd/{pkg}/_boundary_fault_injection.py",
        "import atdd.coach  # injected boundary crossing\n",
    )

    viols = _evaluate(graph_rooted_at(clean_convention_graph, tmp_path))
    assert any(v["source"].startswith(f"{target_slug}:") for v in viols), (
        f"convention evaluator missed injected crossing in {target_slug}: {viols}"
    )

    # Post-condition: the real tree was never written to.
    assert _evaluate(clean_convention_graph) == []
