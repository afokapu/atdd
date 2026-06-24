# URN: test:validate-conventions:boundary-variants:theme_commons_coach_boundary
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

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from atdd.validators.conventions._support.graph_loader import load_composed_graph
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
LEGACY_NODEID = (
    'src/atdd/planner/validators/test_theme_commons_coach_boundary.py'
    '::test_commons_wagons_do_not_import_coach'
)

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
    with fixtures_tmp() as tmp:
        graph = fixtures.build_graph(tmp, fixtures.INVALID_FRAGMENTS["commons_wagon_imports_coach"])
        viols = _evaluate(graph)
    assert viols, "invalid fragment must yield a violation"
    for v in viols:
        assert set(v) <= declared, f"evidence keys {set(v)} escape contract {declared}"
    assert declared == set(FAILURE_EVIDENCE)
    assert root.is_dir()


# --- fixtures (real ConventionGraph fragments) -----------------------------
@contextlib.contextmanager
def fixtures_tmp():
    d = tempfile.mkdtemp(prefix="boundary-fix-")
    try:
        yield Path(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_valid_fragment_commons_no_coach_import_clean() -> None:
    with fixtures_tmp() as tmp:
        graph = fixtures.build_graph(tmp, fixtures.VALID_FRAGMENTS["commons_wagon_no_coach_import"])
        assert _evaluate(graph) == []


def test_valid_fragment_coach_wagon_may_import_coach() -> None:
    with fixtures_tmp() as tmp:
        graph = fixtures.build_graph(tmp, fixtures.VALID_FRAGMENTS["coach_wagon_imports_coach"])
        assert _evaluate(graph) == []


def test_invalid_fragment_commons_imports_coach_caught() -> None:
    with fixtures_tmp() as tmp:
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
    with fixtures_tmp() as tmp:
        graph = fixtures.build_graph(
            tmp, {"wagon": deferred_slug, "theme": "commons", "imports_coach": True}
        )
        assert _evaluate(graph) == []


# --- clean baseline on the REAL composed graph -----------------------------
def test_clean_baseline_real_graph_is_empty() -> None:
    graph = load_composed_graph(_repo_root())
    assert _evaluate(graph) == [], (
        "clean repo must yield zero boundary crossings (deferred wagons excluded)"
    )


# --- fault injection + legacy parity (BOTH must catch) ---------------------
def _run_legacy(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", LEGACY_NODEID, "-q", "-p", "no:cacheprovider"],
        cwd=str(root),
        env={"PYTHONPATH": "src", "PATH": os.environ.get("PATH", "")},
        capture_output=True, text=True,
    )


def test_fault_injection_convention_and_legacy_both_catch() -> None:
    """Inject a coach import under a real non-deferred commons wagon's source
    tree; assert the convention evaluator AND the legacy validator (subprocess)
    BOTH catch it; then revert and confirm both go green again."""
    root = _repo_root()
    graph0 = load_composed_graph(root)

    # Pick a real commons, non-deferred wagon whose src/atdd/<slug> dir does NOT
    # yet exist — so injection is a clean create + delete (fully reversible).
    target_slug = None
    for w in graph0.by_kind("wagon"):
        if w.theme != "commons":
            continue
        slug = w.fields.get("wagon") or w.package
        if slug in DEFERRED_RETHEME_WAGONS:
            continue
        if not (root / "src" / "atdd" / str(slug).replace("-", "_")).exists():
            target_slug = slug
            break
    assert target_slug, "no clean commons wagon available for fault injection"

    src_dir = root / "src" / "atdd" / target_slug.replace("-", "_")
    fault = src_dir / "_boundary_fault_injection.py"

    # Pre-condition: both clean.
    assert _evaluate(load_composed_graph(root)) == []
    pre = _run_legacy(root)
    assert pre.returncode == 0, f"legacy not green pre-injection:\n{pre.stdout}\n{pre.stderr}"

    try:
        src_dir.mkdir(parents=True, exist_ok=True)
        fault.write_text("import atdd.coach  # injected boundary crossing\n", encoding="utf-8")

        # Convention evaluator catches it.
        viols = _evaluate(load_composed_graph(root))
        assert any(v["source"].startswith(f"{target_slug}:") for v in viols), (
            f"convention evaluator missed injected crossing in {target_slug}: {viols}"
        )

        # Legacy validator (subprocess) ALSO catches it.
        post = _run_legacy(root)
        assert post.returncode != 0, (
            f"legacy did not catch injected crossing:\n{post.stdout}\n{post.stderr}"
        )
        assert target_slug in (post.stdout + post.stderr)
    finally:
        # Revert: remove exactly what we created.
        if fault.exists():
            fault.unlink()
        # Remove the dir only if we created it and it's now empty.
        try:
            src_dir.rmdir()
        except OSError:
            pass

    # Post-condition: both green again.
    assert _evaluate(load_composed_graph(root)) == []
    after = _run_legacy(root)
    assert after.returncode == 0, f"legacy not green after revert:\n{after.stdout}\n{after.stderr}"
