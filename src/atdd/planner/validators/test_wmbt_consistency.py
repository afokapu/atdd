"""
Platform tests: WMBT consistency validation.

Validates that WMBT references in wagon manifests and feature files match
the actual WMBT YAML files present in the wagon directory.

Source of truth: WMBT YAML files in plan/{wagon}/*.yaml
"""
import pytest
from pathlib import Path
from typing import Dict, Set, List, Tuple
import yaml

# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
PLAN_DIR = REPO_ROOT / "plan"


@pytest.fixture
def wmbt_files():
    """
    Discover all WMBT files in plan/{wagon}/ directories.

    Returns: Dict[wagon_slug, Set[wmbt_code]]
        e.g., {"generate-identifiers": {"L001", "L002", "P001", "C001", ...}}
    """
    wmbt_map: Dict[str, Set[str]] = {}

    # Pattern: plan/{wagon_dir}/{STEP_CODE}{NNN}.yaml
    # Where STEP_CODE is one of: D, L, P, C, E, M, Y, R, K
    # And NNN is 001-999

    for wagon_dir in PLAN_DIR.iterdir():
        if not wagon_dir.is_dir():
            continue

        # Directory name uses underscores, convert to kebab-case slug
        dir_name = wagon_dir.name
        wagon_slug = dir_name.replace("_", "-")

        wmbt_codes: Set[str] = set()

        # Find all WMBT files matching the pattern
        for yaml_file in wagon_dir.glob("*.yaml"):
            filename = yaml_file.stem  # e.g., "L001", "C005"

            # Check if it matches WMBT pattern: {STEP_CODE}{NNN}
            if len(filename) == 4 and filename[0] in "DLPCEMYRK" and filename[1:].isdigit():
                wmbt_codes.add(filename)

        if wmbt_codes:
            wmbt_map[wagon_slug] = wmbt_codes

    return wmbt_map


@pytest.fixture
def feature_files():
    """
    Discover all feature files in plan/{wagon}/features/*.yaml.

    Returns: List[Tuple[wagon_slug, feature_path, feature_data]]
    """
    features: List[Tuple[str, Path, Dict]] = []

    for wagon_dir in PLAN_DIR.iterdir():
        if not wagon_dir.is_dir():
            continue

        # Directory name uses underscores, convert to kebab-case slug
        dir_name = wagon_dir.name
        wagon_slug = dir_name.replace("_", "-")

        features_dir = wagon_dir / "features"

        if features_dir.exists() and features_dir.is_dir():
            for feature_file in features_dir.glob("*.yaml"):
                try:
                    with open(feature_file) as f:
                        feature_data = yaml.safe_load(f)
                        if feature_data:
                            features.append((wagon_slug, feature_file, feature_data))
                except Exception as e:
                    pytest.fail(f"Failed to load feature file {feature_file}: {e}")

    return features


@pytest.mark.platform
@pytest.mark.e2e
def test_wagon_manifest_wmbt_codes_exist_as_files(wagon_manifests, wmbt_files):
    """
    SPEC-PLATFORM-WMBT-0001: Wagon manifest WMBT codes must exist as YAML files

    Given: Wagon manifest with wmbt section listing codes
    When: Checking if WMBT files exist
    Then: Each WMBT code in manifest has corresponding {CODE}.yaml file
          in the wagon's directory

    Source of Truth: WMBT YAML files in plan/{wagon}/{CODE}.yaml
    """
    errors = []

    for path, manifest in wagon_manifests:
        wagon_slug = manifest.get("wagon", "")
        wmbt_section = manifest.get("wmbt", {})

        if not wmbt_section:
            # No WMBTs declared - skip
            continue

        # Get actual WMBT files for this wagon
        actual_wmbts = wmbt_files.get(wagon_slug, set())

        # Check each WMBT code in manifest
        for wmbt_code, statement in wmbt_section.items():
            # Skip metadata fields
            if wmbt_code in ("total", "coverage"):
                continue

            if wmbt_code not in actual_wmbts:
                errors.append(
                    f"Wagon '{wagon_slug}' declares WMBT '{wmbt_code}' in manifest, "
                    f"but file plan/{wagon_slug}/{wmbt_code}.yaml does not exist. "
                    f"Available WMBTs: {sorted(actual_wmbts)}"
                )

    if errors:
        pytest.fail("\n".join(errors))


@pytest.mark.platform
@pytest.mark.e2e
def test_wmbt_files_declared_in_wagon_manifest(wagon_manifests, wmbt_files):
    """
    SPEC-PLATFORM-WMBT-0002: All WMBT files must be declared in wagon manifest

    Given: WMBT YAML files in plan/{wagon}/ directory
    When: Checking wagon manifest wmbt section
    Then: Each WMBT file has corresponding entry in manifest wmbt section

    Source of Truth: WMBT YAML files in plan/{wagon}/{CODE}.yaml
    """
    errors = []

    for wagon_slug, actual_wmbts in wmbt_files.items():
        # Find corresponding wagon manifest
        wagon_manifest = None
        for path, manifest in wagon_manifests:
            if manifest.get("wagon") == wagon_slug:
                wagon_manifest = manifest
                break

        if not wagon_manifest:
            # Wagon manifest not found - skip (other tests will catch this)
            continue

        wmbt_section = wagon_manifest.get("wmbt", {})
        declared_wmbts = set(k for k in wmbt_section.keys() if k not in ("total", "coverage"))

        # Check if all file WMBTs are declared
        undeclared = actual_wmbts - declared_wmbts

        if undeclared:
            errors.append(
                f"Wagon '{wagon_slug}' has WMBT files {sorted(undeclared)} "
                f"but they are not declared in the manifest wmbt section. "
                f"Declared WMBTs: {sorted(declared_wmbts)}"
            )

    if errors:
        pytest.fail("\n".join(errors))


@pytest.mark.platform
@pytest.mark.e2e
def test_feature_acceptance_criteria_match_wmbt_files(feature_files, wmbt_files):
    """
    SPEC-PLATFORM-WMBT-0003: Feature acceptance_criteria codes must match actual WMBT files

    Given: Feature files with acceptance_criteria section
    When: Checking acceptance criteria URNs
    Then: Each acceptance criteria code references an existing WMBT file

    Source of Truth: WMBT YAML files in plan/{wagon}/{CODE}.yaml

    Note: Acceptance criteria URNs follow pattern: acc:{wagon}:{WMBT_CODE}-{TEST_TYPE}-{NNN}
          We extract {WMBT_CODE} and verify it exists as a file
    """
    errors = []

    for wagon_slug, feature_path, feature_data in feature_files:
        acceptance_criteria = feature_data.get("acceptance_criteria", {})

        if not acceptance_criteria:
            # No acceptance criteria - skip
            continue

        # Get actual WMBT files for this wagon
        actual_wmbts = wmbt_files.get(wagon_slug, set())

        # Check each acceptance criterion
        for criterion_key, criterion_data in acceptance_criteria.items():
            urn = criterion_data.get("urn", "")

            if not urn:
                errors.append(
                    f"Feature '{feature_path.name}' in wagon '{wagon_slug}' "
                    f"has acceptance criterion '{criterion_key}' without URN"
                )
                continue

            # Parse URN: acc:{wagon}:{WMBT_CODE}-{TEST_TYPE}-{NNN}
            # Example: acc:generate-identifiers:L001-UNIT-001
            # Extract WMBT_CODE: L001
            parts = urn.split(":")
            if len(parts) < 3:
                errors.append(
                    f"Feature '{feature_path.name}' in wagon '{wagon_slug}' "
                    f"has malformed acceptance criterion URN: {urn}"
                )
                continue

            # Get the code part: "L001-UNIT-001"
            code_part = parts[2]

            # Extract WMBT code (before first hyphen): "L001"
            wmbt_code = code_part.split("-")[0]

            # Verify this WMBT file exists
            if wmbt_code not in actual_wmbts:
                errors.append(
                    f"Feature '{feature_path.name}' in wagon '{wagon_slug}' "
                    f"references WMBT '{wmbt_code}' (from URN: {urn}), "
                    f"but file plan/{wagon_slug}/{wmbt_code}.yaml does not exist. "
                    f"Available WMBTs: {sorted(actual_wmbts)}"
                )

    if errors:
        pytest.fail("\n".join(errors))


@pytest.mark.platform
@pytest.mark.e2e
def test_wmbt_file_urns_match_expected_pattern(wmbt_files):
    """
    SPEC-PLATFORM-WMBT-0004: WMBT files must have URNs matching their filename

    Given: WMBT YAML file at plan/{wagon}/{CODE}.yaml
    When: Reading the file's URN field
    Then: URN must be wmbt:{wagon}:{CODE}

    Source of Truth: WMBT YAML files in plan/{wagon}/{CODE}.yaml
    """
    errors = []

    for wagon_slug, wmbt_codes in wmbt_files.items():
        # Convert kebab-case slug to underscore directory name
        dir_name = wagon_slug.replace("-", "_")
        wagon_dir = PLAN_DIR / dir_name

        for wmbt_code in wmbt_codes:
            wmbt_file = wagon_dir / f"{wmbt_code}.yaml"

            try:
                with open(wmbt_file) as f:
                    wmbt_data = yaml.safe_load(f)

                if not wmbt_data:
                    errors.append(
                        f"WMBT file {wmbt_file} is empty or invalid YAML"
                    )
                    continue

                # Check URN
                urn = wmbt_data.get("urn", "")
                expected_urn = f"wmbt:{wagon_slug}:{wmbt_code}"

                if urn != expected_urn:
                    errors.append(
                        f"WMBT file {wmbt_file} has URN '{urn}', "
                        f"but expected '{expected_urn}' based on filename"
                    )

            except Exception as e:
                errors.append(
                    f"Failed to read WMBT file {wmbt_file}: {e}"
                )

    if errors:
        pytest.fail("\n".join(errors))


@pytest.mark.platform
@pytest.mark.e2e
def test_wmbt_count_matches_actual_files(wagon_manifests, wmbt_files):
    """
    SPEC-PLATFORM-WMBT-0005: Wagon manifest 'total' field must match actual WMBT count

    Given: Wagon manifest with wmbt.total field
    When: Counting actual WMBT files in wagon directory
    Then: wmbt.total equals the count of WMBT files

    Source of Truth: WMBT YAML files in plan/{wagon}/{CODE}.yaml
    """
    errors = []

    for path, manifest in wagon_manifests:
        wagon_slug = manifest.get("wagon", "")
        wmbt_section = manifest.get("wmbt", {})

        if not wmbt_section:
            # No WMBTs - skip
            continue

        declared_total = wmbt_section.get("total", 0)
        actual_wmbts = wmbt_files.get(wagon_slug, set())
        actual_count = len(actual_wmbts)

        if declared_total != actual_count:
            errors.append(
                f"Wagon '{wagon_slug}' declares wmbt.total={declared_total}, "
                f"but has {actual_count} actual WMBT files: {sorted(actual_wmbts)}"
            )

    if errors:
        pytest.fail("\n".join(errors))
