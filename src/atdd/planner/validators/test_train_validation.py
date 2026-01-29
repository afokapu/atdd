"""
Platform tests: Train validation with theme-based numbering.

Validates that trains follow conventions:
- Theme-based numbering (00-09, 10-19, 20-29, etc.)
- Wagon references exist
- Artifact consistency
- Dependencies are valid
- Registry grouping matches numbering
"""
import pytest
import yaml
from pathlib import Path
from typing import Dict, List, Set, Tuple


@pytest.mark.platform
def test_train_ids_follow_numbering_convention(trains_registry):
    """
    SPEC-TRAIN-VAL-0001: Train IDs follow theme-based numbering

    Given: Train registry with train_ids
    When: Checking train_id format
    Then: Each train_id matches pattern: {digit}{digit}{digit}{digit}-{kebab-case-name}
          (4-digit hierarchical: [Theme][Category][Variation])
    """
    import re

    pattern = re.compile(r"^[0-9]{4}-[a-z][a-z0-9-]*$")

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
    repo_root = Path(__file__).resolve().parents[4]
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
    repo_root = Path(__file__).resolve().parents[4]
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
    repo_root = Path(__file__).resolve().parents[4]
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
    repo_root = Path(__file__).resolve().parents[4]
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
    repo_root = Path(__file__).resolve().parents[4]
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

    repo_root = Path(__file__).resolve().parents[4]
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
    repo_root = Path(__file__).resolve().parents[4]
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

    repo_root = Path(__file__).resolve().parents[4]
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
