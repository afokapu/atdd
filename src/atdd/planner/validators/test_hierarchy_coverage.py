"""
Planner hierarchy coverage validation.

ATDD Hierarchy Coverage Spec v0.1 - Section 2: Planner Coverage Rules

Validates bidirectional coverage between:
- Trains <-> Wagons (COVERAGE-PLAN-2.1)
- Wagons <-> Features (COVERAGE-PLAN-2.2)
- Features <-> WMBTs (COVERAGE-PLAN-2.3)
- WMBTs <-> Acceptances (COVERAGE-PLAN-2.4)

Architecture:
- Uses shared fixtures from atdd.coach.validators.shared_fixtures
- Phased rollout via atdd.coach.utils.coverage_phase
- Exception handling via .atdd/config.yaml coverage.exceptions
"""

import pytest
import yaml
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.coverage_phase import (
    CoveragePhase,
    should_enforce,
    emit_coverage_warning
)


# Path constants
REPO_ROOT = find_repo_root()
PLAN_DIR = REPO_ROOT / "plan"


# ============================================================================
# COVERAGE-PLAN-2.1: Train <-> Wagon Coverage
# ============================================================================


@pytest.mark.planner
def test_all_wagons_in_at_least_one_train(
    wagon_manifests,
    wagon_to_train_mapping,
    coverage_exceptions
):
    """
    COVERAGE-PLAN-2.1a: Every wagon appears in at least one train.

    Given: All wagon manifests in plan/
    When: Checking train participant references
    Then: Every wagon slug appears in at least one train's participants
          (unless in wagons_not_in_train allow-list or status:draft)
    """
    allowed_wagons = set(coverage_exceptions.get("wagons_not_in_train", []))
    violations = []

    for path, manifest in wagon_manifests:
        wagon_slug = manifest.get("wagon", "")
        status = manifest.get("status", "")

        # Skip draft wagons
        if status == "draft":
            continue

        # Skip allowed exceptions
        if wagon_slug in allowed_wagons:
            continue

        # Check if wagon is in any train
        if wagon_slug not in wagon_to_train_mapping:
            violations.append(
                f"{wagon_slug}: not referenced by any train (path: {path.relative_to(REPO_ROOT)})"
            )

    if violations:
        if should_enforce(CoveragePhase.PLANNER_TESTER_ENFORCEMENT):
            pytest.fail(
                f"COVERAGE-PLAN-2.1a: Wagons not in any train:\n  " +
                "\n  ".join(violations) +
                "\n\nAdd to train participants or coverage.exceptions.wagons_not_in_train"
            )
        else:
            for violation in violations:
                emit_coverage_warning(
                    "COVERAGE-PLAN-2.1a",
                    violation,
                    CoveragePhase.PLANNER_TESTER_ENFORCEMENT
                )


@pytest.mark.planner
def test_all_train_wagon_refs_exist(train_files, wagon_manifests):
    """
    COVERAGE-PLAN-2.1b: Every train wagon participant has manifest.

    Given: Train YAML files with wagon: participants
    When: Checking wagon references
    Then: Every referenced wagon has a manifest in plan/
    """
    # Build set of existing wagon slugs
    wagon_slugs = {manifest.get("wagon", "") for _, manifest in wagon_manifests}

    violations = []

    for train_path, train_data in train_files:
        train_id = train_data.get("train_id", train_path.stem)
        participants = train_data.get("participants", [])

        for participant in participants:
            if isinstance(participant, str) and participant.startswith("wagon:"):
                wagon_slug = participant.replace("wagon:", "")
                if wagon_slug not in wagon_slugs:
                    violations.append(
                        f"{train_id}: references non-existent wagon '{wagon_slug}'"
                    )

    if violations:
        if should_enforce(CoveragePhase.PLANNER_TESTER_ENFORCEMENT):
            pytest.fail(
                f"COVERAGE-PLAN-2.1b: Train wagon references to non-existent wagons:\n  " +
                "\n  ".join(violations)
            )
        else:
            for violation in violations:
                emit_coverage_warning(
                    "COVERAGE-PLAN-2.1b",
                    violation,
                    CoveragePhase.PLANNER_TESTER_ENFORCEMENT
                )


# ============================================================================
# COVERAGE-PLAN-2.2: Wagon <-> Feature Coverage
# ============================================================================


@pytest.mark.planner
def test_all_features_in_wagon_manifest(feature_files, wagon_manifests, coverage_exceptions):
    """
    COVERAGE-PLAN-2.2a: Every feature file referenced in wagon manifest.

    Given: Feature files in plan/*/features/
    When: Checking wagon manifest features[] references
    Then: Every feature file is referenced by its wagon's manifest
    """
    allowed_features = set(coverage_exceptions.get("features_orphaned", []))

    # Build mapping of wagon_dir -> manifest features
    wagon_features: Dict[str, Set[str]] = {}
    for path, manifest in wagon_manifests:
        wagon_dir = path.parent.name
        features_list = manifest.get("features", [])

        feature_slugs = set()
        for feature in features_list:
            if isinstance(feature, dict) and "urn" in feature:
                # URN format: feature:wagon-slug:feature-slug
                urn = feature["urn"]
                parts = urn.split(":")
                if len(parts) >= 3:
                    feature_slugs.add(parts[2])
            elif isinstance(feature, str):
                # Direct slug or URN
                if feature.startswith("feature:"):
                    parts = feature.split(":")
                    if len(parts) >= 3:
                        feature_slugs.add(parts[2])
                else:
                    feature_slugs.add(feature)

        wagon_features[wagon_dir] = feature_slugs

    violations = []

    for path, feature_data in feature_files:
        wagon_dir = path.parent.parent.name
        # Feature filename (snake_case) -> slug (kebab-case)
        feature_filename = path.stem
        feature_slug = feature_filename.replace("_", "-")

        # Also check for URN in feature data
        feature_urn = feature_data.get("urn", "")

        # Skip allowed exceptions
        if feature_urn in allowed_features or feature_slug in allowed_features:
            continue

        # Check if feature is in wagon manifest
        manifest_features = wagon_features.get(wagon_dir, set())
        if feature_slug not in manifest_features:
            violations.append(
                f"{path.relative_to(REPO_ROOT)}: not in wagon manifest features[]"
            )

    if violations:
        if should_enforce(CoveragePhase.PLANNER_TESTER_ENFORCEMENT):
            pytest.fail(
                f"COVERAGE-PLAN-2.2a: Features not in wagon manifest:\n  " +
                "\n  ".join(violations) +
                "\n\nAdd to wagon features[] or coverage.exceptions.features_orphaned"
            )
        else:
            for violation in violations:
                emit_coverage_warning(
                    "COVERAGE-PLAN-2.2a",
                    violation,
                    CoveragePhase.PLANNER_TESTER_ENFORCEMENT
                )


@pytest.mark.planner
def test_all_wagon_feature_refs_exist(wagon_manifests):
    """
    COVERAGE-PLAN-2.2b: Every wagon features[] entry has YAML file.

    Given: Wagon manifests with features[] references
    When: Checking for corresponding files
    Then: Every features[] entry has a YAML file in wagon/features/
    """
    violations = []

    for path, manifest in wagon_manifests:
        wagon_dir = path.parent
        features_dir = wagon_dir / "features"
        features_list = manifest.get("features", [])

        for feature in features_list:
            feature_slug = None

            if isinstance(feature, dict) and "urn" in feature:
                # URN format: feature:wagon-slug:feature-slug
                urn = feature["urn"]
                parts = urn.split(":")
                if len(parts) >= 3:
                    feature_slug = parts[2]
            elif isinstance(feature, str):
                if feature.startswith("feature:"):
                    parts = feature.split(":")
                    if len(parts) >= 3:
                        feature_slug = parts[2]
                else:
                    feature_slug = feature

            if not feature_slug:
                continue

            # Convert slug to filename (kebab-case -> snake_case)
            feature_filename = feature_slug.replace("-", "_") + ".yaml"
            feature_path = features_dir / feature_filename

            if not feature_path.exists():
                wagon_slug = manifest.get("wagon", wagon_dir.name)
                violations.append(
                    f"{wagon_slug}: features[] references '{feature_slug}' but "
                    f"{feature_path.relative_to(REPO_ROOT)} does not exist"
                )

    if violations:
        if should_enforce(CoveragePhase.PLANNER_TESTER_ENFORCEMENT):
            pytest.fail(
                f"COVERAGE-PLAN-2.2b: Wagon feature references without files:\n  " +
                "\n  ".join(violations)
            )
        else:
            for violation in violations:
                emit_coverage_warning(
                    "COVERAGE-PLAN-2.2b",
                    violation,
                    CoveragePhase.PLANNER_TESTER_ENFORCEMENT
                )


# ============================================================================
# COVERAGE-PLAN-2.3: WMBT <-> Feature Coverage
# ============================================================================


@pytest.mark.planner
def test_all_wmbts_in_at_least_one_feature(wmbt_files, feature_files):
    """
    COVERAGE-PLAN-2.3: Every WMBT appears in at least one feature's wmbts.

    Given: WMBT files in plan/*/
    When: Checking feature wmbts[] references
    Then: Every WMBT file is referenced by at least one feature
    """
    # Build set of all WMBT references from features
    referenced_wmbts: Set[str] = set()

    for path, feature_data in feature_files:
        wmbts_list = feature_data.get("wmbts", [])
        for wmbt_ref in wmbts_list:
            if isinstance(wmbt_ref, dict) and "urn" in wmbt_ref:
                referenced_wmbts.add(wmbt_ref["urn"])
            elif isinstance(wmbt_ref, str):
                referenced_wmbts.add(wmbt_ref)

    violations = []

    for path, wmbt_data in wmbt_files:
        wmbt_urn = wmbt_data.get("urn", "")
        status = wmbt_data.get("status", "")

        # Skip draft WMBTs
        if status == "draft":
            continue

        # Check both URN and file-based reference
        wmbt_id = path.stem  # e.g., "D001"
        wagon_slug = path.parent.name.replace("_", "-")

        # Try various reference formats
        is_referenced = (
            wmbt_urn in referenced_wmbts or
            f"wmbt:{wagon_slug}:{wmbt_id}" in referenced_wmbts or
            wmbt_id in referenced_wmbts
        )

        if not is_referenced:
            violations.append(
                f"{path.relative_to(REPO_ROOT)}: not referenced by any feature"
            )

    if violations:
        if should_enforce(CoveragePhase.PLANNER_TESTER_ENFORCEMENT):
            pytest.fail(
                f"COVERAGE-PLAN-2.3: WMBTs not in any feature:\n  " +
                "\n  ".join(violations) +
                "\n\nAdd WMBT to a feature's wmbts[] list"
            )
        else:
            for violation in violations:
                emit_coverage_warning(
                    "COVERAGE-PLAN-2.3",
                    violation,
                    CoveragePhase.PLANNER_TESTER_ENFORCEMENT
                )


# ============================================================================
# COVERAGE-PLAN-2.4: WMBT <-> Acceptance Coverage
# ============================================================================


@pytest.mark.planner
def test_all_wmbts_have_acceptances(wmbt_files, coverage_exceptions):
    """
    COVERAGE-PLAN-2.4: Every non-draft WMBT has at least one acceptance.

    Given: WMBT files in plan/*/
    When: Checking acceptances[]
    Then: Every WMBT (except draft) has at least one acceptance
    """
    allowed_wmbts = set(coverage_exceptions.get("wmbts_without_acceptance", []))
    violations = []

    for path, wmbt_data in wmbt_files:
        wmbt_urn = wmbt_data.get("urn", "")
        status = wmbt_data.get("status", "")
        acceptances = wmbt_data.get("acceptances", [])

        # Skip draft WMBTs
        if status == "draft":
            continue

        # Skip allowed exceptions
        if wmbt_urn in allowed_wmbts:
            continue

        # Check for acceptances
        if not acceptances or len(acceptances) == 0:
            violations.append(
                f"{path.relative_to(REPO_ROOT)}: no acceptances defined"
            )

    if violations:
        if should_enforce(CoveragePhase.PLANNER_TESTER_ENFORCEMENT):
            pytest.fail(
                f"COVERAGE-PLAN-2.4: WMBTs without acceptances:\n  " +
                "\n  ".join(violations) +
                "\n\nAdd acceptances or coverage.exceptions.wmbts_without_acceptance"
            )
        else:
            for violation in violations:
                emit_coverage_warning(
                    "COVERAGE-PLAN-2.4",
                    violation,
                    CoveragePhase.PLANNER_TESTER_ENFORCEMENT
                )


# ============================================================================
# COVERAGE SUMMARY
# ============================================================================


@pytest.mark.planner
def test_planner_coverage_summary(
    wagon_manifests,
    feature_files,
    wmbt_files,
    wagon_to_train_mapping
):
    """
    COVERAGE-PLAN-SUMMARY: Report planner coverage statistics.

    This test always passes but reports coverage metrics for visibility.
    """
    # Count wagons in trains
    wagons_in_trains = len(wagon_to_train_mapping)
    total_wagons = len(wagon_manifests)

    # Count features
    total_features = len(feature_files)

    # Count WMBTs with acceptances
    wmbts_with_acceptances = sum(
        1 for _, data in wmbt_files
        if data.get("acceptances") and len(data.get("acceptances", [])) > 0
    )
    total_wmbts = len(wmbt_files)

    # Report summary (always passes)
    summary = (
        f"\n\nPlanner Coverage Summary:\n"
        f"  Wagons in trains: {wagons_in_trains}/{total_wagons}\n"
        f"  Features defined: {total_features}\n"
        f"  WMBTs with acceptances: {wmbts_with_acceptances}/{total_wmbts}"
    )

    # This test always passes - it's informational
    assert True, summary
