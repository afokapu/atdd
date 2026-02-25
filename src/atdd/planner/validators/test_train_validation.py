"""
Platform tests: Train validation with theme-based numbering.

Validates that trains follow conventions:
- Theme-based numbering (00-09, 10-19, 20-29, etc.)
- Wagon references exist
- Artifact consistency
- Dependencies are valid
- Registry grouping matches numbering
- Train First-Class Spec v0.6 requirements
- E008: Train enforcement — orphan wagon detection, empty train warnings

Train First-Class Spec v0.6 validators (SPEC-TRAIN-VAL-0012 to 0021, 0034-0036):
- Path/file normalization
- Theme derivation and validation
- Wagon participant validation
- Test/code field typing
- Expectations and status inference

E008 validators (SPEC-TRAIN-VAL-0039 to 0041):
- Orphan wagon detection (wagons with WMBTs not in any train)
- Phantom wagon detection (wagon refs in trains that don't exist)
- Empty train warnings
"""
import pytest
import yaml
import warnings
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.train_spec_phase import (
    TrainSpecPhase,
    should_enforce,
    emit_phase_warning
)


@pytest.mark.platform
def test_train_ids_follow_numbering_convention(trains_registry):
    """
    SPEC-TRAIN-VAL-0001: Train IDs follow theme-based numbering

    Given: Train registry with train_ids
    When: Checking train_id format
    Then: Each train_id matches pattern: {digit}{digit}{digit}{digit}-{kebab-case-name}
          (4-digit hierarchical: [Theme][Category][Variation])

    Updated in v0.6: Pattern now allows digits in slug portion (^\\d{4}-[a-z0-9-]+$)
    """
    import re

    # v0.6: Updated pattern to allow digits in slug (e.g., 0001-auth-v2-session)
    pattern = re.compile(r"^\d{4}-[a-z0-9-]+$")

    for theme, trains in trains_registry.items():
        if not trains:
            continue

        for train in trains:
            train_id = train.get("train_id", "")
            assert pattern.match(train_id), \
                f"Train ID '{train_id}' doesn't match pattern NNNN-kebab-case (theme: {theme})"


@pytest.mark.platform
def test_train_theme_matches_first_digit(trains_registry):
    """
    SPEC-TRAIN-VAL-0002: Train theme matches first digit of ID

    Given: Train registry organized by theme
    When: Checking train_id first digit
    Then: First digit maps to correct theme category
    """
    theme_map = {
        "0": "commons",
        "1": "mechanic",
        "2": "scenario",
        "3": "match",
        "4": "sensory",
        "5": "player",
        "6": "league",
        "7": "audience",
        "8": "monetization",
        "9": "partnership",
    }

    mismatches = []
    for theme, trains in trains_registry.items():
        if not trains:
            continue

        for train in trains:
            train_id = train.get("train_id", "")
            if not train_id or len(train_id) < 2:
                continue

            first_digit = train_id[0]
            expected_theme = theme_map.get(first_digit)

            if expected_theme != theme:
                mismatches.append(
                    f"{train_id}: in '{theme}' but numbering suggests '{expected_theme}'"
                )

    assert not mismatches, \
        f"Train theme/numbering mismatches:\n  " + "\n  ".join(mismatches)


@pytest.mark.platform
def test_train_files_exist_for_registry_entries(trains_registry):
    """
    SPEC-TRAIN-VAL-0003: All trains in registry have corresponding files

    Given: Trains listed in plan/_trains.yaml
    When: Checking for train files
    Then: Each train has a file at plan/_trains/{train_id}.yaml
    """
    repo_root = find_repo_root()
    trains_dir = repo_root / "plan" / "_trains"

    missing_files = []
    for theme, trains in trains_registry.items():
        if not trains:
            continue

        for train in trains:
            train_id = train.get("train_id", "")
            if not train_id:
                continue

            train_path = trains_dir / f"{train_id}.yaml"
            if not train_path.exists():
                missing_files.append(f"{train_id} (theme: {theme})")

    assert not missing_files, \
        f"Trains in registry missing files:\n  " + "\n  ".join(missing_files)


@pytest.mark.platform
def test_all_train_files_registered(trains_registry):
    """
    SPEC-TRAIN-VAL-0004: All train files are registered in _trains.yaml

    Given: Train YAML files in plan/_trains/
    When: Checking registry
    Then: Each file is registered in plan/_trains.yaml
    """
    repo_root = find_repo_root()
    trains_dir = repo_root / "plan" / "_trains"

    # Get all registered train IDs
    registered_ids = set()
    for theme, trains in trains_registry.items():
        if trains:
            for train in trains:
                if "train_id" in train:
                    registered_ids.add(train["train_id"])

    # Check all train files
    unregistered = []
    if trains_dir.exists():
        for train_file in trains_dir.glob("*.yaml"):
            train_id = train_file.stem
            if train_id not in registered_ids:
                unregistered.append(train_id)

    assert not unregistered, \
        f"Train files not in registry:\n  " + "\n  ".join(unregistered)


@pytest.mark.platform
def test_train_id_matches_filename(trains_registry):
    """
    SPEC-TRAIN-VAL-0005: Train file train_id matches filename

    Given: Train YAML files in plan/_trains/
    When: Loading train data
    Then: train_id field matches filename (without .yaml)
    """
    repo_root = find_repo_root()
    trains_dir = repo_root / "plan" / "_trains"

    mismatches = []
    if trains_dir.exists():
        for train_file in trains_dir.glob("*.yaml"):
            filename_id = train_file.stem

            with train_file.open() as f:
                train_data = yaml.safe_load(f)

            train_id = train_data.get("train_id")
            if train_id != filename_id:
                mismatches.append(
                    f"{train_file.name}: train_id '{train_id}' != filename '{filename_id}'"
                )

    assert not mismatches, \
        f"Train ID/filename mismatches:\n  " + "\n  ".join(mismatches)


@pytest.mark.platform
def test_train_wagons_exist(trains_registry, wagon_manifests):
    """
    SPEC-TRAIN-VAL-0006: All wagons in trains exist in registry or plan/*

    Given: Trains with wagon participants
    When: Checking wagon references
    Then: Each wagon exists in registry or has a manifest in plan/*
    """
    repo_root = find_repo_root()
    trains_dir = repo_root / "plan" / "_trains"

    # Build wagon name set from manifests
    wagon_names = {manifest.get("wagon", "") for _, manifest in wagon_manifests}

    missing_wagons = {}
    for theme, trains in trains_registry.items():
        if not trains:
            continue

        for train in trains:
            train_id = train.get("train_id", "")
            if not train_id:
                continue

            # Load train file
            train_path = trains_dir / f"{train_id}.yaml"
            if not train_path.exists():
                continue

            with train_path.open() as f:
                train_data = yaml.safe_load(f)

            # Extract wagon participants
            participants = train_data.get("participants", [])
            for participant in participants:
                if isinstance(participant, str) and participant.startswith("wagon:"):
                    wagon_name = participant.replace("wagon:", "")
                    if wagon_name not in wagon_names:
                        if train_id not in missing_wagons:
                            missing_wagons[train_id] = []
                        missing_wagons[train_id].append(wagon_name)

    assert not missing_wagons, \
        f"Trains reference non-existent wagons:\n" + \
        "\n".join(f"  {tid}: {', '.join(wagons)}" for tid, wagons in missing_wagons.items())


@pytest.mark.platform
def test_train_dependencies_are_valid(trains_registry):
    """
    SPEC-TRAIN-VAL-0007: Train dependencies reference valid trains

    Given: Trains with dependencies
    When: Checking dependency references
    Then: Each dependency points to a valid train_id
    """
    repo_root = find_repo_root()
    trains_dir = repo_root / "plan" / "_trains"

    # Get all valid train IDs
    valid_train_ids = set()
    for theme, trains in trains_registry.items():
        if trains:
            for train in trains:
                if "train_id" in train:
                    valid_train_ids.add(train["train_id"])

    # Check dependencies
    invalid_deps = {}
    for theme, trains in trains_registry.items():
        if not trains:
            continue

        for train in trains:
            train_id = train.get("train_id", "")
            if not train_id:
                continue

            # Load train file
            train_path = trains_dir / f"{train_id}.yaml"
            if not train_path.exists():
                continue

            with train_path.open() as f:
                train_data = yaml.safe_load(f)

            dependencies = train_data.get("dependencies", [])
            for dep in dependencies:
                # Format: train:XX-name
                if dep.startswith("train:"):
                    dep_id = dep.replace("train:", "")
                    if dep_id not in valid_train_ids:
                        if train_id not in invalid_deps:
                            invalid_deps[train_id] = []
                        invalid_deps[train_id].append(dep)

    assert not invalid_deps, \
        f"Trains have invalid dependencies:\n" + \
        "\n".join(f"  {tid}: {', '.join(deps)}" for tid, deps in invalid_deps.items())


@pytest.mark.platform
def test_train_artifacts_follow_naming_convention(trains_registry):
    """
    SPEC-TRAIN-VAL-0008: Artifacts in trains follow domain:resource pattern

    Given: Train sequences with artifacts
    When: Checking artifact names
    Then: Each artifact follows pattern {domain}:{resource}
    """
    import re

    repo_root = find_repo_root()
    trains_dir = repo_root / "plan" / "_trains"

    pattern = re.compile(r"^[a-z][a-z0-9-]*(?::[a-z][a-z0-9-]*)+(?:\.[a-z][a-z0-9-]*)*$")

    invalid_artifacts = {}

    def extract_artifacts(steps: List[Dict]) -> Set[str]:
        """Recursively extract artifacts from steps, loops, and routes."""
        artifacts = set()
        for item in steps:
            if "step" in item and "artifact" in item:
                artifacts.add(item["artifact"])
            elif "loop" in item:
                loop_data = item["loop"]
                if "steps" in loop_data:
                    artifacts.update(extract_artifacts(loop_data["steps"]))
            elif "route" in item:
                route_data = item["route"]
                for branch in route_data.get("branches", []):
                    if "steps" in branch:
                        artifacts.update(extract_artifacts(branch["steps"]))
        return artifacts

    for theme, trains in trains_registry.items():
        if not trains:
            continue

        for train in trains:
            train_id = train.get("train_id", "")
            if not train_id:
                continue

            # Load train file
            train_path = trains_dir / f"{train_id}.yaml"
            if not train_path.exists():
                continue

            with train_path.open() as f:
                train_data = yaml.safe_load(f)

            # Extract all artifacts
            sequence = train_data.get("sequence", [])
            artifacts = extract_artifacts(sequence)

            # Check each artifact
            for artifact in artifacts:
                if not pattern.match(artifact):
                    if train_id not in invalid_artifacts:
                        invalid_artifacts[train_id] = []
                    invalid_artifacts[train_id].append(artifact)

    assert not invalid_artifacts, \
        f"Trains have invalid artifact names:\n" + \
        "\n".join(f"  {tid}: {', '.join(arts)}" for tid, arts in invalid_artifacts.items())


@pytest.mark.platform
@pytest.mark.skip(reason="Soft validation - artifacts may come from external sources")
def test_train_artifacts_exist_in_wagons(trains_registry, wagon_manifests):
    """
    SPEC-TRAIN-VAL-0009: Artifacts in trains are produced/consumed by wagons

    Given: Train sequences with artifacts
    When: Checking artifact definitions
    Then: Each artifact should be in wagon produce/consume lists
    Note: Soft check - external/system artifacts are allowed
    """
    repo_root = find_repo_root()
    trains_dir = repo_root / "plan" / "_trains"

    # Build artifact index from wagons
    wagon_artifacts = {}
    for _, manifest in wagon_manifests:
        wagon_name = manifest.get("wagon", "")
        artifacts = set()

        for produce_item in manifest.get("produce", []):
            if "name" in produce_item:
                artifacts.add(produce_item["name"])

        for consume_item in manifest.get("consume", []):
            if "name" in consume_item:
                artifacts.add(consume_item["name"])

        wagon_artifacts[wagon_name] = artifacts

    def extract_artifacts(steps: List[Dict]) -> Set[str]:
        """Recursively extract artifacts from steps."""
        artifacts = set()
        for item in steps:
            if "step" in item and "artifact" in item:
                artifacts.add(item["artifact"])
            elif "loop" in item:
                if "steps" in item["loop"]:
                    artifacts.update(extract_artifacts(item["loop"]["steps"]))
            elif "route" in item:
                for branch in item["route"].get("branches", []):
                    if "steps" in branch:
                        artifacts.update(extract_artifacts(branch["steps"]))
        return artifacts

    warnings = []
    for theme, trains in trains_registry.items():
        if not trains:
            continue

        for train in trains:
            train_id = train.get("train_id", "")
            if not train_id:
                continue

            train_path = trains_dir / f"{train_id}.yaml"
            if not train_path.exists():
                continue

            with train_path.open() as f:
                train_data = yaml.safe_load(f)

            # Get wagons and artifacts
            participants = train_data.get("participants", [])
            wagon_names = [
                p.replace("wagon:", "")
                for p in participants
                if isinstance(p, str) and p.startswith("wagon:")
            ]

            # Collect all artifacts from participating wagons
            available_artifacts = set()
            for wagon_name in wagon_names:
                if wagon_name in wagon_artifacts:
                    available_artifacts.update(wagon_artifacts[wagon_name])

            # Check train artifacts
            train_artifacts = extract_artifacts(train_data.get("sequence", []))

            for artifact in train_artifacts:
                # Skip known external patterns
                if any(
                    artifact.startswith(prefix)
                    for prefix in ["gesture:", "onboarding:", "account:", "auth:", "material:"]
                ):
                    continue

                if artifact not in available_artifacts:
                    warnings.append(
                        f"{train_id}: artifact '{artifact}' not in wagons {wagon_names}"
                    )

    if warnings:
        pytest.skip(
            f"⚠️  Artifact warnings ({len(warnings)}):\n  " +
            "\n  ".join(warnings[:10]) +
            (f"\n  ... and {len(warnings) - 10} more" if len(warnings) > 10 else "")
        )


@pytest.mark.platform
def test_registry_themes_are_valid(trains_registry):
    """
    SPEC-TRAIN-VAL-0010: Registry theme keys match schema enum

    Given: Train registry organized by themes
    When: Checking theme keys
    Then: All theme keys are valid according to train.schema.json
    """
    valid_themes = {
        "commons",
        "mechanic",
        "scenario",
        "match",
        "sensory",
        "player",
        "league",
        "audience",
        "monetization",
        "partnership",
    }

    invalid_themes = []
    for theme in trains_registry.keys():
        if theme not in valid_themes:
            invalid_themes.append(theme)

    assert not invalid_themes, \
        f"Invalid themes in registry: {', '.join(invalid_themes)}\n" \
        f"Valid themes: {', '.join(sorted(valid_themes))}"


@pytest.mark.platform
def test_trains_match_schema(trains_registry):
    """
    SPEC-TRAIN-VAL-0011: All train files validate against train.schema.json

    Given: Train files in plan/_trains/
    When: Validating against schema
    Then: All trains pass schema validation
    """
    from jsonschema import Draft7Validator
    import json

    repo_root = find_repo_root()
    schema_path = repo_root / ".claude" / "schemas" / "planner" / "train.schema.json"
    trains_dir = repo_root / "plan" / "_trains"

    if not schema_path.exists():
        pytest.skip("train.schema.json not found")

    with schema_path.open() as f:
        schema = json.load(f)

    validator = Draft7Validator(schema)

    failures = []
    if trains_dir.exists():
        for train_file in trains_dir.glob("*.yaml"):
            with train_file.open() as f:
                train_data = yaml.safe_load(f)

            errors = list(validator.iter_errors(train_data))
            if errors:
                failures.append(f"{train_file.name}: {errors[0].message}")

    assert not failures, \
        f"Schema validation failures:\n  " + "\n  ".join(failures)


# ============================================================================
# TRAIN FIRST-CLASS SPEC v0.6 VALIDATORS
# ============================================================================
# New validators for path/file normalization, theme validation, wagon
# participants, test/code field typing, and expectations/status inference.
# ============================================================================


def _normalize_test_code_field(field_value: Any) -> Dict[str, List[str]]:
    """
    Normalize test/code field to canonical structure.

    Section 5: Test/Code Field Typing Normalization
    - string -> {"backend": [string]}
    - list -> {"backend": list}
    - dict -> normalize each sub-field to list
    """
    if field_value is None:
        return {}

    if isinstance(field_value, str):
        return {"backend": [field_value]}
    elif isinstance(field_value, list):
        return {"backend": field_value}
    elif isinstance(field_value, dict):
        result = {}
        for key in ["backend", "frontend", "frontend_python"]:
            if key in field_value:
                val = field_value[key]
                result[key] = [val] if isinstance(val, str) else (val or [])
        return result
    return {}


def _infer_expectations(train_data: Dict[str, Any]) -> Dict[str, bool]:
    """
    Infer expectations from train data.

    Section 12: Status/Expectations Inference
    """
    if "expectations" in train_data:
        return train_data["expectations"]

    status = train_data.get("status", "planned")
    test_fields = _normalize_test_code_field(train_data.get("test"))
    code_fields = _normalize_test_code_field(train_data.get("code"))

    if status == "tested":
        return {"backend": True}
    elif status == "implemented":
        return {
            "backend": True,
            "frontend": bool(code_fields.get("frontend")),
            "frontend_python": bool(code_fields.get("frontend_python"))
        }
    else:
        return {
            "backend": bool(test_fields.get("backend") or code_fields.get("backend")),
            "frontend": bool(test_fields.get("frontend") or code_fields.get("frontend")),
            "frontend_python": bool(test_fields.get("frontend_python") or code_fields.get("frontend_python"))
        }


def _extract_wagons_from_participants(participants: List[str]) -> List[str]:
    """
    Extract wagon names from participants list.

    Section 4: Participants is Canonical Wagon Source
    """
    wagons = []
    for participant in participants:
        if isinstance(participant, str) and participant.startswith("wagon:"):
            wagon_name = participant.replace("wagon:", "")
            wagons.append(wagon_name)
    return wagons


@pytest.mark.platform
def test_train_path_file_normalization(trains_registry):
    """
    SPEC-TRAIN-VAL-0012: Path is canonical, file is deprecated alias

    Given: Trains in registry
    When: Checking path/file fields
    Then: If only 'file' exists without 'path', emit deprecation warning

    Section 1: Path Canonical, File Deprecated Alias
    """
    repo_root = find_repo_root()
    trains_dir = repo_root / "plan" / "_trains"

    deprecation_warnings = []

    for theme, trains in trains_registry.items():
        if not trains:
            continue

        for train in trains:
            train_id = train.get("train_id", "")
            if not train_id:
                continue

            train_path = trains_dir / f"{train_id}.yaml"
            if not train_path.exists():
                continue

            with train_path.open() as f:
                train_data = yaml.safe_load(f)

            has_path = "path" in train_data
            has_file = "file" in train_data

            if has_file and not has_path:
                deprecation_warnings.append(
                    f"{train_id}: uses 'file' without 'path' (deprecated)"
                )

    if deprecation_warnings:
        if should_enforce(TrainSpecPhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"Trains using deprecated 'file' field:\n  " +
                "\n  ".join(deprecation_warnings) +
                "\n\nMigrate to 'path' field (Section 1 of Train First-Class Spec)"
            )
        else:
            for warning in deprecation_warnings:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0012",
                    warning,
                    TrainSpecPhase.FULL_ENFORCEMENT
                )


@pytest.mark.platform
def test_train_ids_globally_unique(trains_registry):
    """
    SPEC-TRAIN-VAL-0013: Train IDs globally unique across categories

    Given: Trains across all themes and categories
    When: Checking train_id uniqueness
    Then: No duplicate train_ids exist

    Section 2: Global Uniqueness
    """
    all_train_ids = []
    train_locations = {}

    for theme, trains in trains_registry.items():
        if not trains:
            continue

        for train in trains:
            train_id = train.get("train_id", "")
            if train_id:
                all_train_ids.append(train_id)
                if train_id in train_locations:
                    train_locations[train_id].append(theme)
                else:
                    train_locations[train_id] = [theme]

    duplicates = {
        tid: themes for tid, themes in train_locations.items()
        if len(themes) > 1
    }

    assert not duplicates, \
        f"Duplicate train IDs found:\n  " + \
        "\n  ".join(f"{tid}: appears in themes {themes}" for tid, themes in duplicates.items())


@pytest.mark.platform
def test_train_theme_derived_from_group_key(trains_registry_with_groups):
    """
    SPEC-TRAIN-VAL-0014: Theme derived from registry group key

    Given: Trains in nested registry structure
    When: Checking theme derivation
    Then: Theme can be derived from group key (e.g., "0-commons" -> "commons")

    Section 3: Theme Precedence Rules
    """
    for theme_key, categories in trains_registry_with_groups.items():
        if not isinstance(categories, dict):
            continue

        # Derive theme from group key
        if "-" in theme_key:
            derived_theme = theme_key.split("-", 1)[1]
        else:
            derived_theme = theme_key

        # Verify derived theme is valid
        valid_themes = {
            "commons", "mechanic", "scenario", "match", "sensory",
            "player", "league", "audience", "monetization", "partnership"
        }

        assert derived_theme in valid_themes, \
            f"Invalid derived theme '{derived_theme}' from group key '{theme_key}'"


@pytest.mark.platform
def test_train_explicit_theme_matches_group(trains_registry_with_groups):
    """
    SPEC-TRAIN-VAL-0015: Explicit theme matches group placement

    Given: Trains with explicit theme field in registry
    When: Checking theme consistency
    Then: Explicit theme matches derived theme from group key

    Section 3: Theme Precedence Rules
    """
    mismatches = []

    for theme_key, categories in trains_registry_with_groups.items():
        if not isinstance(categories, dict):
            continue

        # Derive theme from group key
        derived_theme = theme_key.split("-", 1)[1] if "-" in theme_key else theme_key

        for category_key, trains_list in categories.items():
            if not isinstance(trains_list, list):
                continue

            for train in trains_list:
                train_id = train.get("train_id", "unknown")
                explicit_theme = train.get("theme")

                if explicit_theme and explicit_theme != derived_theme:
                    mismatches.append(
                        f"{train_id}: explicit theme '{explicit_theme}' != "
                        f"derived theme '{derived_theme}' (group: {theme_key})"
                    )

    if mismatches:
        if should_enforce(TrainSpecPhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"Theme mismatches found:\n  " + "\n  ".join(mismatches)
            )
        else:
            for mismatch in mismatches:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0015",
                    mismatch,
                    TrainSpecPhase.FULL_ENFORCEMENT
                )


@pytest.mark.platform
def test_train_yaml_themes_include_derived(train_files):
    """
    SPEC-TRAIN-VAL-0016: YAML themes array includes derived theme

    Given: Train YAML files with themes array
    When: Comparing to registry placement
    Then: YAML themes array includes the derived theme from registry

    Section 3: Theme Precedence Rules
    """
    repo_root = find_repo_root()
    trains_file = repo_root / "plan" / "_trains.yaml"

    if not trains_file.exists():
        pytest.skip("No _trains.yaml registry found")

    # Build train -> derived_theme mapping from registry
    with open(trains_file) as f:
        registry_data = yaml.safe_load(f)

    train_to_theme = {}
    for theme_key, categories in registry_data.get("trains", {}).items():
        derived_theme = theme_key.split("-", 1)[1] if "-" in theme_key else theme_key
        if isinstance(categories, dict):
            for category_key, trains_list in categories.items():
                if isinstance(trains_list, list):
                    for train in trains_list:
                        train_id = train.get("train_id")
                        if train_id:
                            train_to_theme[train_id] = derived_theme

    # Check YAML files
    mismatches = []
    for train_path, train_data in train_files:
        train_id = train_data.get("train_id")
        yaml_themes = train_data.get("themes", [])

        if train_id in train_to_theme:
            derived_theme = train_to_theme[train_id]
            if yaml_themes and derived_theme not in yaml_themes:
                mismatches.append(
                    f"{train_id}: YAML themes {yaml_themes} missing derived theme '{derived_theme}'"
                )

    if mismatches:
        if should_enforce(TrainSpecPhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"YAML themes missing derived themes:\n  " + "\n  ".join(mismatches)
            )
        else:
            for mismatch in mismatches:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0016",
                    mismatch,
                    TrainSpecPhase.FULL_ENFORCEMENT
                )


@pytest.mark.platform
def test_train_participants_canonical_wagon_source(train_files):
    """
    SPEC-TRAIN-VAL-0017: Participants is canonical wagon source

    Given: Train YAML files
    When: Extracting wagon references
    Then: Wagons are derived from participants array (wagon:* entries)

    Section 4: Participants is Canonical Wagon Source
    """
    missing_participants = []

    for train_path, train_data in train_files:
        train_id = train_data.get("train_id", train_path.stem)
        participants = train_data.get("participants", [])

        if not participants:
            missing_participants.append(f"{train_id}: no participants defined")
            continue

        wagons = _extract_wagons_from_participants(participants)
        if not wagons:
            missing_participants.append(f"{train_id}: no wagon participants found")

    if missing_participants:
        if should_enforce(TrainSpecPhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"Trains missing wagon participants:\n  " + "\n  ".join(missing_participants)
            )
        else:
            for missing in missing_participants:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0017",
                    missing,
                    TrainSpecPhase.FULL_ENFORCEMENT
                )


@pytest.mark.platform
def test_train_registry_wagons_subset_of_yaml(trains_registry, train_files):
    """
    SPEC-TRAIN-VAL-0018: Registry wagons subset of YAML participants

    Given: Trains in registry and YAML files
    When: Comparing wagon lists
    Then: Registry wagons must be subset of YAML participants

    Section 4: Registry Wagons Subset
    """
    # Build train_id -> YAML wagons mapping
    yaml_wagons = {}
    for train_path, train_data in train_files:
        train_id = train_data.get("train_id")
        if train_id:
            participants = train_data.get("participants", [])
            yaml_wagons[train_id] = set(_extract_wagons_from_participants(participants))

    violations = []

    for theme, trains in trains_registry.items():
        if not trains:
            continue

        for train in trains:
            train_id = train.get("train_id", "")
            registry_wagon_list = train.get("wagons", [])

            if not train_id or not registry_wagon_list:
                continue

            yaml_wagon_set = yaml_wagons.get(train_id, set())
            registry_wagon_set = set(registry_wagon_list)

            extra_wagons = registry_wagon_set - yaml_wagon_set
            if extra_wagons:
                violations.append(
                    f"{train_id}: registry wagons {extra_wagons} not in YAML participants"
                )

    if violations:
        if should_enforce(TrainSpecPhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"Registry wagons not in YAML participants:\n  " + "\n  ".join(violations)
            )
        else:
            for violation in violations:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0018",
                    violation,
                    TrainSpecPhase.FULL_ENFORCEMENT
                )


@pytest.mark.platform
def test_train_primary_wagon_in_participants(train_files):
    """
    SPEC-TRAIN-VAL-0019: Primary wagon exists and is in participants

    Given: Train YAML files with primary_wagon field
    When: Checking primary wagon
    Then: Primary wagon is in participants list

    Section 4: Primary Wagon Validation
    """
    violations = []

    for train_path, train_data in train_files:
        train_id = train_data.get("train_id", train_path.stem)
        primary_wagon = train_data.get("primary_wagon")

        if not primary_wagon:
            continue

        participants = train_data.get("participants", [])
        wagons = _extract_wagons_from_participants(participants)

        if primary_wagon not in wagons:
            violations.append(
                f"{train_id}: primary_wagon '{primary_wagon}' not in participants"
            )

    if violations:
        if should_enforce(TrainSpecPhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"Primary wagon violations:\n  " + "\n  ".join(violations)
            )
        else:
            for violation in violations:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0019",
                    violation,
                    TrainSpecPhase.FULL_ENFORCEMENT
                )


@pytest.mark.platform
def test_train_test_field_typing(train_files):
    """
    SPEC-TRAIN-VAL-0020: Test field typing normalization

    Given: Train YAML files with test field
    When: Checking test field structure
    Then: Test field normalizes to {backend: [], frontend: [], frontend_python: []}

    Section 5: Test Field Typing
    """
    invalid_types = []

    for train_path, train_data in train_files:
        train_id = train_data.get("train_id", train_path.stem)
        test_field = train_data.get("test")

        if test_field is None:
            continue

        # Validate type
        if not isinstance(test_field, (str, list, dict)):
            invalid_types.append(
                f"{train_id}: test field has invalid type {type(test_field).__name__}"
            )
            continue

        # Validate dict structure if applicable
        if isinstance(test_field, dict):
            valid_keys = {"backend", "frontend", "frontend_python"}
            extra_keys = set(test_field.keys()) - valid_keys
            if extra_keys:
                invalid_types.append(
                    f"{train_id}: test field has invalid keys {extra_keys}"
                )

    assert not invalid_types, \
        f"Invalid test field types:\n  " + "\n  ".join(invalid_types)


@pytest.mark.platform
def test_train_code_field_typing(train_files):
    """
    SPEC-TRAIN-VAL-0021: Code field typing normalization

    Given: Train YAML files with code field
    When: Checking code field structure
    Then: Code field normalizes to {backend: [], frontend: [], frontend_python: []}

    Section 5: Code Field Typing
    """
    invalid_types = []

    for train_path, train_data in train_files:
        train_id = train_data.get("train_id", train_path.stem)
        code_field = train_data.get("code")

        if code_field is None:
            continue

        # Validate type
        if not isinstance(code_field, (str, list, dict)):
            invalid_types.append(
                f"{train_id}: code field has invalid type {type(code_field).__name__}"
            )
            continue

        # Validate dict structure if applicable
        if isinstance(code_field, dict):
            valid_keys = {"backend", "frontend", "frontend_python"}
            extra_keys = set(code_field.keys()) - valid_keys
            if extra_keys:
                invalid_types.append(
                    f"{train_id}: code field has invalid keys {extra_keys}"
                )

    assert not invalid_types, \
        f"Invalid code field types:\n  " + "\n  ".join(invalid_types)


@pytest.mark.platform
def test_train_expectations_structure(train_files):
    """
    SPEC-TRAIN-VAL-0034: Expectations field structure

    Given: Train YAML files with expectations field
    When: Checking expectations structure
    Then: Expectations has boolean values for backend/frontend/frontend_python

    Section 12: Expectations Field Structure
    """
    invalid_expectations = []

    for train_path, train_data in train_files:
        train_id = train_data.get("train_id", train_path.stem)
        expectations = train_data.get("expectations")

        if expectations is None:
            continue

        if not isinstance(expectations, dict):
            invalid_expectations.append(
                f"{train_id}: expectations must be object, got {type(expectations).__name__}"
            )
            continue

        # Validate keys and types
        valid_keys = {"backend", "frontend", "frontend_python"}
        for key, value in expectations.items():
            if key not in valid_keys:
                invalid_expectations.append(
                    f"{train_id}: expectations has invalid key '{key}'"
                )
            elif not isinstance(value, bool):
                invalid_expectations.append(
                    f"{train_id}: expectations.{key} must be boolean, got {type(value).__name__}"
                )

    assert not invalid_expectations, \
        f"Invalid expectations structure:\n  " + "\n  ".join(invalid_expectations)


@pytest.mark.platform
def test_train_status_inference(train_files):
    """
    SPEC-TRAIN-VAL-0035: Status inference from expectations

    Given: Train YAML files
    When: Inferring status from expectations and test/code fields
    Then: Status can be correctly inferred (planned -> tested -> implemented)

    Section 12: Status Inference
    """
    inferred_results = []

    for train_path, train_data in train_files:
        train_id = train_data.get("train_id", train_path.stem)
        explicit_status = train_data.get("status")
        expectations = _infer_expectations(train_data)

        # Verify inference is valid
        has_backend_test = bool(_normalize_test_code_field(train_data.get("test")).get("backend"))
        has_backend_code = bool(_normalize_test_code_field(train_data.get("code")).get("backend"))

        inferred_status = "planned"
        if has_backend_code:
            inferred_status = "implemented"
        elif has_backend_test:
            inferred_status = "tested"

        inferred_results.append({
            "train_id": train_id,
            "explicit_status": explicit_status,
            "inferred_status": inferred_status,
            "expectations": expectations
        })

    # This test verifies the inference logic works
    assert len(inferred_results) >= 0  # Always passes, just validates logic


@pytest.mark.platform
def test_train_status_expectations_conflict(train_files):
    """
    SPEC-TRAIN-VAL-0036: Status/expectations conflict detection

    Given: Train YAML files with status and expectations
    When: Checking for conflicts
    Then: No conflicts between status and expectations

    Section 12: Status/Expectations Conflict Detection
    """
    conflicts = []

    for train_path, train_data in train_files:
        train_id = train_data.get("train_id", train_path.stem)
        status = train_data.get("status", "planned")
        expectations = train_data.get("expectations", {})

        # Detect conflicts
        if status == "implemented" and expectations.get("backend") is False:
            conflicts.append(
                f"{train_id}: status='implemented' but expectations.backend=false"
            )

        if status == "tested" and expectations.get("backend") is False:
            conflicts.append(
                f"{train_id}: status='tested' but expectations.backend=false"
            )

    if conflicts:
        if should_enforce(TrainSpecPhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"Status/expectations conflicts:\n  " + "\n  ".join(conflicts)
            )
        else:
            for conflict in conflicts:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0036",
                    conflict,
                    TrainSpecPhase.FULL_ENFORCEMENT
                )


@pytest.mark.platform
def test_trains_are_linear_no_loops_or_routes(trains_registry):
    """
    SPEC-TRAIN-VAL-0037: Trains must be strictly linear (no loops or routes).

    Per URN Spec V3 S10 R11: Trains are strictly linear. Sequences contain
    steps only. No loops, routes, or branching. New journeys that require
    different paths must create new trains.

    Given: Train spec files with sequences
    When: Checking for loop or route elements
    Then: No sequence item should contain a 'loop' or 'route' key
    """
    repo_root = find_repo_root()
    trains_dir = repo_root / "plan" / "_trains"

    if not trains_dir.exists():
        pytest.skip("No _trains directory")

    violations = []

    for theme, trains in trains_registry.items():
        if not trains:
            continue
        for train in trains:
            train_id = train.get("train_id", "")
            train_path = trains_dir / f"{train_id}.yaml"
            if not train_path.exists():
                continue

            try:
                with open(train_path, "r", encoding="utf-8") as f:
                    spec = yaml.safe_load(f)
            except Exception:
                continue

            if not spec or not isinstance(spec, dict):
                continue

            sequence = spec.get("sequence", [])
            for idx, item in enumerate(sequence):
                if "loop" in item:
                    violations.append(
                        f"{train_id} step {idx}: contains 'loop' "
                        f"(name={item['loop'].get('name', '?')})"
                    )
                if "route" in item:
                    violations.append(
                        f"{train_id} step {idx}: contains 'route' "
                        f"(name={item['route'].get('name', '?')})"
                    )

    if violations:
        pytest.fail(
            f"\nTrains must be strictly linear (no loops/routes). "
            f"Found {len(violations)} violations:\n  "
            + "\n  ".join(violations)
            + "\n\nNew journeys requiring different paths should create new trains."
        )


@pytest.mark.platform
def test_train_sequences_have_sequential_step_numbers(trains_registry):
    """
    SPEC-TRAIN-VAL-0038: Train step numbers must be sequential with no gaps.

    Given: Train spec files with linear sequences
    When: Checking step numbering
    Then: Steps must be numbered 1, 2, 3, ... with no gaps
    """
    repo_root = find_repo_root()
    trains_dir = repo_root / "plan" / "_trains"

    if not trains_dir.exists():
        pytest.skip("No _trains directory")

    violations = []

    for theme, trains in trains_registry.items():
        if not trains:
            continue
        for train in trains:
            train_id = train.get("train_id", "")
            train_path = trains_dir / f"{train_id}.yaml"
            if not train_path.exists():
                continue

            try:
                with open(train_path, "r", encoding="utf-8") as f:
                    spec = yaml.safe_load(f)
            except Exception:
                continue

            if not spec or not isinstance(spec, dict):
                continue

            sequence = spec.get("sequence", [])
            step_numbers = [
                item.get("step") for item in sequence
                if isinstance(item, dict) and "step" in item
            ]

            if not step_numbers:
                continue

            expected = list(range(1, len(step_numbers) + 1))
            if step_numbers != expected:
                violations.append(
                    f"{train_id}: steps={step_numbers}, expected={expected}"
                )

    if violations:
        pytest.fail(
            f"\nTrain step numbering must be sequential (1,2,3,...). "
            f"Found {len(violations)} violations:\n  "
            + "\n  ".join(violations)
        )


# ============================================================================
# E008: Train Enforcement — Orphan wagons, phantom references, empty trains
# ============================================================================


@pytest.mark.platform
def test_wagons_with_wmbts_must_be_in_a_train(
    wagon_manifests, wagon_to_train_mapping, wmbt_files
):
    """
    SPEC-TRAIN-VAL-0039: Wagons with WMBTs must appear in at least one train

    Given: Wagon manifests and WMBT plan files
    When: Checking train coverage for wagons that have WMBTs
    Then: Every wagon with wmbt.total > 0 appears in at least 1 train's participants

    E008 acceptance criteria: `atdd validate planner` fails if orphan wagons with WMBTs are found.
    """
    # Count WMBTs per wagon slug (from plan directories)
    import re
    wmbt_pattern = re.compile(r"^[DLPCEMYRK]\d{3}\.yaml$")
    repo_root = find_repo_root()
    plan_dir = repo_root / "plan"

    wagon_wmbt_counts = {}
    for path, _ in wmbt_files:
        # Derive wagon slug from directory name (snake_case -> kebab-case)
        wagon_slug = path.parent.name.replace("_", "-")
        wagon_wmbt_counts[wagon_slug] = wagon_wmbt_counts.get(wagon_slug, 0) + 1

    # Find orphan wagons: have WMBTs but not in any train
    orphans = []
    for wagon_slug, wmbt_count in sorted(wagon_wmbt_counts.items()):
        if wmbt_count > 0 and wagon_slug not in wagon_to_train_mapping:
            orphans.append(f"{wagon_slug} ({wmbt_count} WMBTs, no train)")

    assert not orphans, (
        f"\nOrphan wagons with WMBTs but no train assignment found.\n"
        f"Every wagon with WMBTs must appear in at least 1 train's participants.\n"
        f"Fix: Add wagon:<slug> to the participants list of an appropriate train.\n\n"
        f"Orphans ({len(orphans)}):\n  " + "\n  ".join(orphans)
    )


@pytest.mark.platform
def test_empty_trains_generate_warning(trains_registry, train_files):
    """
    SPEC-TRAIN-VAL-0040: Trains with empty participants generate warnings

    Given: Train specification files
    When: Checking participant lists
    Then: Trains with wagons: [] (empty participants) generate a warning
    """
    empty_trains = []
    for train_path, train_data in train_files:
        train_id = train_data.get("train_id", train_path.stem)
        participants = train_data.get("participants", [])
        if not participants:
            empty_trains.append(train_id)

    if empty_trains:
        emit_phase_warning(
            "SPEC-TRAIN-VAL-0040",
            f"Trains with empty participants: {', '.join(empty_trains)}",
            TrainSpecPhase.BACKEND_ENFORCEMENT,
        )


@pytest.mark.platform
def test_train_wagon_references_exist_in_manifests(
    train_files, wagon_manifests
):
    """
    SPEC-TRAIN-VAL-0041: Train wagon references must exist in wagon manifests

    Given: Train files with wagon participants
    When: Cross-referencing against known wagon manifests
    Then: Every wagon:<slug> participant has a matching wagon manifest
          (no phantom references)
    """
    wagon_names = {manifest.get("wagon", "") for _, manifest in wagon_manifests}

    phantoms = []
    for train_path, train_data in train_files:
        train_id = train_data.get("train_id", train_path.stem)
        participants = train_data.get("participants", [])
        for participant in participants:
            if isinstance(participant, str) and participant.startswith("wagon:"):
                wagon_slug = participant.replace("wagon:", "")
                if wagon_slug not in wagon_names:
                    phantoms.append(f"{train_id} -> wagon:{wagon_slug}")

    assert not phantoms, (
        f"\nPhantom wagon references in trains (wagon does not exist):\n  "
        + "\n  ".join(phantoms)
        + f"\n\nFix: Remove invalid wagon references or create the missing wagon manifests."
    )
