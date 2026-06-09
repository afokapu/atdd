# URN: test:govern-lifecycle:config-driven-four-tier-validators:E047-UNIT-001-toolkit-four-tier-feature-discovered-and-analyzed
# Acceptance: acc:govern-lifecycle:E047-UNIT-001-toolkit-four-tier-feature-discovered-and-analyzed
# Acceptance: acc:govern-lifecycle:E047-UNIT-002-toolkit-import-resolves-against-src-root-no-false-unwired-violation
# Acceptance: acc:govern-lifecycle:E047-UNIT-003-coder-validators-fixtures-excluded-from-toolkit-discovery
# WMBT: wmbt:govern-lifecycle:E047
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E047 — config-drive the composition-completeness validator onto the toolkit.

The composition validator hardcodes ``repo_root / "python"`` for both the
discovery root (where feature trees live) and the import-resolution base. The
toolkit's own four-tier features live under ``src/atdd`` and import as
``atdd.<wagon>.<feature>.src.<layer>...`` (resolving against the ``src``
import-root). These tests pin the config-driven seam:

* a real toolkit four-tier feature (#865 enforce-surface-conformance) is
  discovered and its qualified ``atdd.`` imports RESOLVE against the ``src``
  import-root (so it is not falsely reported as a wall of unwired layers — the
  25-false-violations regression observed on #955);
* ``coder/validators/fixtures/`` is excluded so the intentionally-broken
  negative composition fixtures cannot self-trigger.

RED state: ``resolve_scan_roots`` / ``ScanRoot`` and the import_root-aware
``build_python_graph`` / ``analyze_python_root`` do not exist yet.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coder.validators._toolkit_roots import ScanRoot, resolve_scan_roots
from atdd.coder.validators.test_composition_completeness import (
    analyze_python_root,
    build_feature_contexts,
    build_python_graph,
)

pytestmark = [pytest.mark.platform]

REPO_ROOT = find_repo_root()
TOOLKIT_CONFIG = {"code": {"toolkit": "src/atdd"}}

# A real, complete toolkit four-tier feature (shipped by #865).
_F865_FEATURE_DIR = (
    REPO_ROOT
    / "src/atdd/consolidate_coach_workspace/enforce_surface_conformance"
)


def _toolkit_scan_root() -> ScanRoot:
    roots = resolve_scan_roots(TOOLKIT_CONFIG, REPO_ROOT)
    toolkit = [r for r in roots if r.discovery_root == REPO_ROOT / "src/atdd"]
    assert toolkit, "code.toolkit must yield a toolkit ScanRoot"
    return toolkit[0]


def test_toolkit_scan_root_carries_src_import_root_and_atdd_prefix():
    """E047-UNIT-001: the toolkit ScanRoot reconciles discovery vs import root.

    discovery_root = src/atdd (where wagons live); import_root = src (where the
    ``atdd`` package resolves); import_prefix = "atdd".
    """
    scan_root = _toolkit_scan_root()
    assert scan_root.discovery_root == REPO_ROOT / "src/atdd"
    assert scan_root.import_root == REPO_ROOT / "src"
    assert scan_root.import_prefix.strip(".") == "atdd"


def test_toolkit_four_tier_feature_discovered_and_analyzed():
    """E047-UNIT-001: enforce-surface-conformance is discovered under src/atdd."""
    scan_root = _toolkit_scan_root()
    contexts = build_feature_contexts(REPO_ROOT, "python", scan_root.discovery_root)
    discovered = {ctx.feature_dir for ctx in contexts}
    assert _F865_FEATURE_DIR in discovered, (
        "the toolkit four-tier feature must be discovered once code.toolkit is honored"
    )
    f865 = next(c for c in contexts if c.feature_dir == _F865_FEATURE_DIR)
    assert any(f865.layer_files[layer] for layer in ("domain", "application", "integration")), (
        "the validator must actually be reading the toolkit layer source files"
    )


def test_qualified_atdd_import_resolves_against_src_import_root():
    """E047-UNIT-002: composition.py's qualified ``atdd.`` imports become real edges.

    With the hardcoded ``python`` base the edge never resolves (every layer looks
    unconsumed → false violations). With import_root = src it resolves.
    """
    scan_root = _toolkit_scan_root()
    graph = build_python_graph(
        REPO_ROOT,
        discovery_root=scan_root.discovery_root,
        import_root=scan_root.import_root,
    )
    composition = _F865_FEATURE_DIR / "composition.py"
    use_case = (
        _F865_FEATURE_DIR / "src/application/apply_layout_use_case.py"
    )
    assert composition in graph, "composition.py must be in the toolkit graph"
    assert use_case in graph.get(composition, set()), (
        "the qualified atdd.<wagon> import must resolve against the src import-root"
    )


def test_wired_toolkit_feature_has_no_false_unwired_violation():
    """E047-UNIT-002: the genuinely-wired #865 feature yields no consumer violation."""
    scan_root = _toolkit_scan_root()
    violations = analyze_python_root(REPO_ROOT, scan_root)
    f865_consumer_violations = [
        v
        for v in violations
        if v.rule_id == "coder.refactor.composition-consumer"
        and "enforce_surface_conformance" in v.location
    ]
    assert not f865_consumer_violations, (
        "a fully-wired toolkit feature must not be reported as unwired:\n"
        + "\n".join(f"{v.location}: {v.detail}" for v in f865_consumer_violations)
    )


def test_coder_validators_fixtures_excluded_from_toolkit_discovery():
    """E047-UNIT-003: negative fixtures under coder/validators/fixtures/ are skipped."""
    scan_root = _toolkit_scan_root()
    contexts = build_feature_contexts(REPO_ROOT, "python", scan_root.discovery_root)
    offenders = [
        ctx.feature_dir
        for ctx in contexts
        if "coder/validators/fixtures" in ctx.feature_dir.as_posix()
    ]
    assert not offenders, (
        "no feature context may be rooted under coder/validators/fixtures: "
        f"{offenders}"
    )
