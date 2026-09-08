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
from atdd.coder.validators.tests._four_tier_exemplar import (
    NO_FOUR_TIER_FEATURE,
    find_four_tier_feature,
)

pytestmark = [pytest.mark.platform]

REPO_ROOT = find_repo_root()


def _toolkit_root():
    roots = resolve_scan_roots(load_atdd_config(REPO_ROOT), REPO_ROOT)
    toolkit = [r for r in roots if r.import_prefix]
    if not toolkit:
        pytest.skip("no code.toolkit configured in this repo")
    return toolkit[0]


def _four_tier_feature(scan_root):
    """The four-tier feature under scan, or skip when none exists.

    Skips on absence of the *subject*, never on the identity of the repo.
    """
    feature = find_four_tier_feature(scan_root.discovery_root)
    if feature is None:
        pytest.skip(NO_FOUR_TIER_FEATURE)
    return feature


def test_real_toolkit_composition_scan_discovers_and_resolves():
    """E047-SMOKE-001: live src/atdd composition scan discovers + resolves a four-tier feature."""
    scan_root = _toolkit_root()
    feature_dir = _four_tier_feature(scan_root)
    violations = analyze_python_root(REPO_ROOT, scan_root)
    locations = {v.location for v in violations}

    # The composition-root-wired tiers resolved their atdd. edges — no false
    # unwired. `application` and `integration` are the tiers the composition root
    # wires together, so a violation located in either means the wiring was not
    # resolved by the scan.
    rel = feature_dir.relative_to(scan_root.discovery_root).as_posix()
    wired_false_positives = [
        loc
        for loc in locations
        if rel in loc
        and ("/src/application/" in loc or "/src/integration/" in loc)
    ]
    assert not wired_false_positives, (
        f"wired toolkit files falsely flagged as unwired: {wired_false_positives}"
    )


def test_real_toolkit_boundaries_finder_over_live_tree():
    """E048-SMOKE-001: live src/atdd boundaries finder enumerates real files, skips fixtures."""
    scan_root = _toolkit_root()
    impls = find_implementation_files(roots=[scan_root])
    posix = {p.as_posix() for p in impls}

    # Fixture exclusion is not exemplar-specific — it stays live unconditionally.
    assert not any("coder/validators/fixtures" in p for p in posix), (
        "negative fixtures must be excluded from the live toolkit scan"
    )

    # Discovering a real implementation file does need a real feature to point at.
    feature_dir = _four_tier_feature(scan_root)
    application = feature_dir / "src" / "application"
    expected = {p.as_posix() for p in application.glob("*.py") if p.name != "__init__.py"}
    assert expected & posix, (
        f"a real toolkit implementation file under {application} must be discovered"
    )
