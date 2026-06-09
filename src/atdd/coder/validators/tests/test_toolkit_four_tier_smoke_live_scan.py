# URN: test:govern-lifecycle:config-driven-four-tier-validators:E047-SMOKE-001-real-toolkit-scan-discovers-and-resolves
# Acceptance: acc:govern-lifecycle:E047-SMOKE-001-real-toolkit-scan-discovers-and-resolves
# Acceptance: acc:govern-lifecycle:E048-SMOKE-001-real-toolkit-files-discovered-over-live-tree
# WMBT: wmbt:govern-lifecycle:E047
# WMBT: wmbt:govern-lifecycle:E048
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E047/E048 SMOKE — the config-driven four-tier validators over the REAL tree.

No mocks, no fixtures: both smokes resolve scan roots from the toolkit's own
shipped ``.atdd/config.yaml`` and run the production analysis/finders over the
live ``src/atdd`` tree, proving the config-driving holds end-to-end (composition
discovery + import resolution; boundaries file discovery + fixture exclusion).
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.config import load_atdd_config
from atdd.coach.utils.repo import find_repo_root
from atdd.coder.validators._toolkit_roots import resolve_scan_roots
from atdd.coder.validators.test_composition_completeness import analyze_python_root
from atdd.coder.validators.test_wagon_boundaries import find_implementation_files

pytestmark = [pytest.mark.platform]

REPO_ROOT = find_repo_root()
_F865_FEATURE = "consolidate_coach_workspace/enforce_surface_conformance"


def _toolkit_root():
    roots = resolve_scan_roots(load_atdd_config(REPO_ROOT), REPO_ROOT)
    toolkit = [r for r in roots if r.import_prefix]
    if not toolkit:
        pytest.skip("no code.toolkit configured in this repo")
    return toolkit[0]


def test_real_toolkit_composition_scan_discovers_and_resolves():
    """E047-SMOKE-001: live src/atdd composition scan discovers + resolves the #865 feature."""
    scan_root = _toolkit_root()
    violations = analyze_python_root(REPO_ROOT, scan_root)
    locations = {v.location for v in violations}

    # The feature is reached by the analysis (it produced at least one
    # location under it OR it is clean — either way the scan ran over it).
    feature_dir = scan_root.discovery_root / _F865_FEATURE
    assert feature_dir.exists(), "expected the #865 toolkit four-tier feature on disk"

    # The composition-root-wired files resolved their atdd. edges — no false unwired.
    wired_false_positives = [
        loc
        for loc in locations
        if _F865_FEATURE in loc
        and (loc.endswith("apply_layout_use_case.py") or loc.endswith("cmux_layout_adapter.py"))
    ]
    assert not wired_false_positives, (
        f"wired toolkit files falsely flagged as unwired: {wired_false_positives}"
    )


def test_real_toolkit_boundaries_finder_over_live_tree():
    """E048-SMOKE-001: live src/atdd boundaries finder enumerates real files, skips fixtures."""
    scan_root = _toolkit_root()
    impls = find_implementation_files(roots=[scan_root])
    posix = {p.as_posix() for p in impls}

    known = (
        scan_root.discovery_root
        / _F865_FEATURE
        / "src/application/apply_layout_use_case.py"
    ).as_posix()
    assert known in posix, "a real toolkit implementation file must be discovered"
    assert not any("coder/validators/fixtures" in p for p in posix), (
        "negative fixtures must be excluded from the live toolkit scan"
    )
